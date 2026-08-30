"""Feature rules — charm capabilities an operator expects but rarely gets."""

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

    This applies to every charm, not only Kubernetes ones. The substrate
    changes how you would otherwise go and look (``kubectl exec`` versus
    ``juju ssh`` and ``snap list``), not whether the version is worth
    reporting, and machine charms report it at half the rate Kubernetes
    charms do.

    Charms with no workload to version — integrators, configurators,
    proxies, interface placeholders — are the real exception, and this
    rule does not try to detect them. Nothing in the metadata declares
    "I have a workload" outside of ``containers:``, and every code-side
    proxy measured against the corpus (``operator_libs_linux``, snap, apt,
    systemd, ``subprocess``) fires at the population's base rate, so it
    separates nothing. Rather than guess, the rule asks such a charm to
    say so once::

        # charmlint: file-ignore[FEATURES-005]

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
        sources = list(context.charm_sources())
        # No source to read is not evidence of a missing call.
        if not sources:
            return []
        if any(_sets_workload_version(module) for module in sources):
            return []
        # ``containers:`` is still the most specific thing to point at when
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
