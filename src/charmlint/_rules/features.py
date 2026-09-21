"""Feature rules — charm capabilities an operator expects."""

import ast

from .. import _ast
from .. import _models as models
from ._base import Rule

# The two ways a charm reports a workload version, one per framework:
# ``ops.Unit.set_workload_version`` and, for a reactive charm built on
# charmhelpers, ``hookenv.application_version_set``. They set the same Juju
# field, so either satisfies this rule — a reactive charm that already
# reports its version is not missing anything, and flagging it because it
# reports it through the other framework's API would be a false positive.
#
# Both are matched on the called name alone rather than on the receiver.
# ``set_workload_version`` is reached as ``self.unit.…``, as
# ``self.model.unit.…`` and through a local the charm bound earlier
# (``unit = self.unit``); ``application_version_set`` is reached as
# ``hookenv.…`` and, imported directly, as a bare name. This is the same
# reasoning ``_ast.observers`` applies to ``framework.observe``: the names
# are specific enough that a same-named method on an unrelated object is
# not a realistic worry, and matching loosely errs towards silence.
_VERSION_CALLS = frozenset({"set_workload_version", "application_version_set"})

# Third-party helpers that drive the workload themselves and set its version
# as part of doing so. They arrive as pip dependencies rather than as files in
# the charm tree, so there is no call for the check above to find; importing
# one is the evidence that the version does get set.
#
# The entries here are the COS worker module, whose ``Worker`` calls
# ``unit.set_workload_version(...)`` on every reconcile, under both the
# spelling it has now and the ``cosl`` one it shipped under before it moved
# to its own distribution. Each is deliberately the module rather than the
# class, so that both constructing a ``Worker`` and subclassing one count —
# the COS worker charms do one each. ``coordinated_workers.coordinator`` is
# *not* listed: ``Coordinator`` does not set a version, and the coordinator
# charms are real findings.
_WORKLOAD_VERSION_SETTERS = frozenset(
    {"coordinated_workers.worker", "cosl.coordinated_workers.worker"}
)

# Charm-name suffixes that say the charm has no workload of its own. By
# Canonical's naming guidelines an integrator hands another charm the
# details of an external service, a configurator writes a fragment of
# another charm's configuration, and an interface repository carries a
# library with a sample charm attached: in each case there is nothing
# running whose version could be read. Of the 30 such charms in the hyrum
# cache, none declares a non-empty ``containers:``, drives a Pebble layer,
# or installs a snap or deb, so the suffix is taken as the charm saying so
# in place of the ``file-ignore`` it would otherwise have to write.
#
# The name comes from the metadata rather than from the directory or the
# repository: a charm need not sit at the root of a repository, need not
# be in one at all, and a monorepo holds several under one repository name.
_NO_WORKLOAD_SUFFIXES = ("-integrator", "-configurator", "-interface")


def _called_name(func: ast.expr) -> str | None:
    """The bare name a call expression invokes, ignoring any receiver."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _sets_workload_version(module: models.Module) -> bool:
    """Whether *module* reports a workload version, directly or by delegation."""
    for call in module.walk(ast.Call):
        if _called_name(call.func) in _VERSION_CALLS:
            return True
    imports = _ast.Imports.of(module)
    return any(imports.imports_module(name) for name in _WORKLOAD_VERSION_SETTERS)


class NoSetWorkloadVersion(Rule):
    """Flag a charm that never reports its workload's version.

    A charm's workload is rarely the charm's own code: it is an OCI image,
    a snap from a channel, a deb, or a set of manifests applied to a
    cluster. Which version of it is actually running is therefore not
    something the reader of ``juju status`` can infer. There is a column
    for exactly that, and unless the charm calls
    ``self.unit.set_workload_version(...)`` — normally once the workload
    is up and can be asked — the column stays empty, and the only way to
    find out is to get a shell on the unit.

    Charms with no workload to version — integrators, configurators,
    proxies, interface placeholders — are the real exception, and the
    rule detects only the ones that say so in their name, through the
    suffixes in :data:`_NO_WORKLOAD_SUFFIXES`. Nothing else in the
    metadata declares "I have a workload" outside of ``containers:``, and
    every code-side proxy measured against the corpus
    (``operator_libs_linux``, snap, apt, systemd, ``subprocess``) fires at
    the population's base rate, so it separates nothing. Rather than guess
    at the rest, the rule asks such a charm to say so once::

        # charmlint: file-ignore[FEATURES-005]

    That leaves the charms whose name gives nothing away — the OpenStack
    storage-backend subordinates, the dashboard and plugin subordinates,
    the library repositories whose sample charm gets enumerated — to the
    comment.

    The call is looked for across the charm's own source (``src/`` and any
    library the charm publishes), matched on the called name alone so that
    every receiver spelling counts: ``self.unit``, ``self.model.unit``, and
    a local the charm bound earlier all resolve. A reactive charm that
    reports its version through charmhelpers' ``application_version_set``
    satisfies the rule too: it is the same Juju field by the other
    framework's name. Charms that delegate the
    workload to a framework which sets the version for them are recognised
    by the import, since the framework is a pip dependency with no source
    in the tree.

    Three routes are still not resolved, each of which would make this a
    false positive: a ``getattr(self.unit, ...)`` lookup, a call made by a
    *vendored* library on the charm's behalf, and any framework not in
    :data:`_WORKLOAD_VERSION_SETTERS`. A charm with no reachable source of
    its own is left alone entirely.
    """

    category = "FEATURES"
    number = 5
    name = "no-set-workload-version"
    description = "Charm never calls set_workload_version()"
    default_severity = models.Severity.INFO
    reference_url = (
        "https://canonical.com/juju/docs/ops/latest/reference/ops/#ops.Unit.set_workload_version"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        name = context.metadata.get("name").value
        if isinstance(name, str) and name.endswith(_NO_WORKLOAD_SUFFIXES):
            return []
        sources = list(context.charm_sources())
        # No source to read is not evidence of a missing call.
        if not sources:
            return []
        if any(_sets_workload_version(module) for module in sources):
            return []
        # ``containers:`` is the most specific thing to point at when
        # the charm has one. For everything else an absent node carries the
        # metadata file with no line, which is what a whole-charm finding
        # wants — and what a ``file-ignore`` needs in order to reach it.
        anchor = context.metadata.get("containers")
        return [
            self.diagnostic(
                "Charm never calls `set_workload_version()` — the workload "
                "version column in `juju status` stays empty",
                path=anchor.source,
                line=anchor.line,
                fix_hint=(
                    "Once the workload is running, ask it its version and call "
                    "`self.unit.set_workload_version(version)`; if this charm has no "
                    "workload to report a version for, silence the rule with "
                    "`# charmlint: file-ignore[FEATURES-005]`"
                ),
            )
        ]


# Strings that report *no* version rather than a wrong one. A charm passes
# one of these to clear the field on teardown, to reset it before a
# reinstall, or as the fallback in its own version helper when the workload
# cannot be asked — 21 of the 24 charms in the hyrum cache that pass a
# placeholder also have a real dynamic call elsewhere, and the three that do
# not are configuration charms with no workload, for which ``n/a`` is an
# honest answer rather than a defect. None of that is what this rule is
# about, so a placeholder is left alone.
_VERSION_PLACEHOLDERS = frozenset({"", "n/a", "none", "unknown"})


def _literal_names(module: models.Module) -> dict[str, str]:
    """Names bound to a string literal and to nothing else, mapped to that literal.

    A name assigned a literal in one branch and a real lookup in another is
    not a hardcoded version, so a name is only treated as constant when
    *every* assignment to it in the file is a string literal. The value is
    carried along because it, not the name, is what decides whether the
    version is a placeholder and what the diagnostic should quote.

    A name assigned a literal more than once keeps the last one, which is
    what the module ends up holding.
    """
    literal: dict[str, str] = {}
    dynamic: set[str] = set()
    for assign in module.walk(ast.Assign):
        constant = isinstance(assign.value, ast.Constant) and isinstance(assign.value.value, str)
        for target in assign.targets:
            if not isinstance(target, ast.Name):
                continue
            if constant:
                literal[target.id] = assign.value.value
            else:
                dynamic.add(target.id)
    return {name: value for name, value in literal.items() if name not in dynamic}


def _hardcoded_version(arg: ast.expr, literal_names: dict[str, str]) -> str | None:
    """The hardcoded version *arg* passes, or ``None`` if it is computed.

    The version is the string that reaches Juju, whether it was written at
    the call or bound to a name first, so a name resolves to its value
    before the placeholder test rather than being tested as a word.
    """
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        value = arg.value
    elif isinstance(arg, ast.Name) and arg.id in literal_names:
        value = literal_names[arg.id]
    else:
        return None
    return None if value.strip().lower() in _VERSION_PLACEHOLDERS else value


class HardcodedWorkloadVersion(Rule):
    """Flag a workload version reported as a constant rather than read.

    The point of the workload version is to say which version is *running*.
    A charm that passes a literal is instead saying which version it was
    written against, and the two part company the first time the image,
    snap or package is bumped without the charm being touched. Nothing
    fails when they do: ``juju status`` keeps reporting the stale number,
    which is worse than the empty column FEATURES-005 is about, because it
    looks like an answer.

    The version should come from the workload: ``pebble exec`` or
    ``subprocess`` asking the binary, a version file the image ships, or
    an API the service exposes — whatever can be read at runtime rather
    than written down.

    A name counts as a constant only when every assignment to it in the
    same file is a string literal, so a charm that seeds a variable with
    a placeholder and then overwrites it with a real lookup is not
    flagged. Neither is the ``self._version() or ""`` fallback idiom, nor
    a placeholder passed on its own: see :data:`_VERSION_PLACEHOLDERS`.
    A constant defined in another module is not followed, which is a
    deliberate gap — it would add false-positive risk for no finding the
    corpus can show.
    """

    category = "FEATURES"
    number = 6
    name = "hardcoded-workload-version"
    description = "Workload version is a hardcoded constant, not read from the workload"
    default_severity = models.Severity.WARNING
    reference_url = (
        "https://canonical.com/juju/docs/ops/latest/reference/ops/#ops.Unit.set_workload_version"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            literal_names = _literal_names(module)
            for call in module.walk(ast.Call):
                if _called_name(call.func) not in _VERSION_CALLS or not call.args:
                    continue
                version = _hardcoded_version(call.args[0], literal_names)
                if version is None:
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"Workload version is hardcoded as `{version}` — it will keep "
                        "being reported after the workload is upgraded",
                        path=module.path,
                        line=call.lineno,
                        fix_hint=(
                            "Read the version from the running workload (ask the binary, "
                            "read a version file the image ships, or query the service) "
                            "rather than writing it into the charm"
                        ),
                    )
                )
        return diagnostics
