"""Features rules — capabilities a charm is expected to have.

Some of these rules are about what the charm tells Juju it needs, and
some about what its Python does at runtime; what they have in common is
a capability an operator expects to be there and has no way to add from
outside the charm.
"""

import ast
import dataclasses
from collections.abc import Iterator

from .. import _ast, _yaml
from .. import _models as models
from ._base import Rule

# A Pebble layer is a mapping with ``services`` in it, and a charm writes
# one two ways: as a dict literal (``{"services": ...}``, passed to
# ``ops.pebble.Layer`` or ``container.add_layer``) or as keyword
# arguments (``ops.pebble.LayerDict(services=..., checks=...)``). The
# same two spellings carry ``checks``, so both sections are read the same
# way, from the mapping keys and from the call keywords.
_SERVICES = "services"
_CHECKS = "checks"

# Keys that mark a mapping as a Pebble layer. A mapping is only taken for
# a layer on the strength of a marker *other than* the section being read:
# ``services`` on its own is what a Kubernetes Service spec has too, and
# ``checks`` is far too common a word to mean Pebble's by itself.
_LAYER_MARKERS = frozenset({_SERVICES, _CHECKS, "summary", "description"})

# Keys that only a Pebble service carries, for a layer that has nothing but
# ``services`` in it. A Kubernetes port spec (``port``, ``targetPort``)
# has none of them.
_SERVICE_MARKERS = frozenset({
    "override",
    "command",
    "startup",
    "after",
    "before",
    "requires",
    "environment",
})

# Keys that only a Pebble check carries. They identify checks written
# away from the layer that will hold them — added to a container on their
# own, or built up in a local before the layer is assembled.
_CHECK_MARKERS = frozenset({
    "override",
    "level",
    "period",
    "timeout",
    "threshold",
    "http",
    "tcp",
    "exec",
})

# The spellings of the typed-dict constructor whose keywords are a layer.
_LAYER_DICT = frozenset({"LayerDict", "pebble.LayerDict", "ops.pebble.LayerDict"})

# The Container methods that only make sense on a workload with checks.
# A charm that reads or drives its checks at runtime plainly has them,
# wherever they were defined.
_CHECK_METHODS = frozenset({"get_check", "get_checks", "start_checks", "stop_checks"})

# A keyword argument whose name mentions Pebble checks hands them to a
# helper that watches them on the charm's behalf. Matched as a substring,
# so that cosl's ``block_if_pebble_checks_failing`` counts.
_CHECK_KEYWORD = "pebble_check"

# The event ops emits when a Pebble check crosses its failure threshold,
# spelled ``<container>_pebble_check_failed``.
_CHECK_FAILED_SUFFIX = "_pebble_check_failed"

# The layer key that hands the failure to Pebble instead: a service that
# names a check under ``on-check-failure`` is restarted by Pebble when
# the check fails, which is a real response to the failure.
_ON_CHECK_FAILURE = "on-check-failure"

# Stands in for an interpolated expression when reading an f-string layer
# as YAML. It can collide with a real scalar, which is harmless only while
# nothing here reads values out of a YAML layer: the rules look at its
# shape, never its scalars, and that has to stay true. An interpolation
# inside a key can still break the parse, which loses that layer.
_PLACEHOLDER = "placeholder"


@dataclasses.dataclass(frozen=True)
class _Site:
    """Where a layer or a check was found, for the diagnostic to point at."""

    path: str
    line: int


def _string_text(node: ast.Constant | ast.JoinedStr) -> str | None:
    """Return the source text of a string literal, f-strings included.

    Each interpolated expression becomes a placeholder scalar, so a layer
    built as an f-string still reads as the YAML document it will be at
    runtime. Anything that is not a string literal returns ``None``.
    """
    if not isinstance(node, ast.JoinedStr):
        return node.value if isinstance(node.value, str) else None
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append(_PLACEHOLDER)
    return "".join(parts)


def _yaml_layer(node: ast.Constant | ast.JoinedStr, section: str, path: str) -> models.Yaml | None:
    """Return a string literal parsed as a layer document, else ``None``.

    Only a string that names *section* is worth handing to the parser, and
    one that does not parse (a fragment, or a template whose placeholders
    broke the indentation) is not a layer that can be read. Line numbers
    in the result point into *path*.
    """
    text = _string_text(node)
    if text is None or f"{section}:" not in text:
        return None
    layer = _yaml.parse(text, path, first_line=node.lineno)
    return layer if layer.present else None


def _is_populated(node: ast.expr | None) -> bool:
    """Whether a layer section holds anything.

    An empty dict literal and an explicit ``None`` are sections the charm
    declared and left empty. Anything else — a populated literal, a
    method call, a name bound elsewhere — is a section with content this
    module cannot see all of, which is not the same as an empty one.
    """
    if node is None:
        return False
    if isinstance(node, ast.Dict):
        return bool(node.keys)
    return not (isinstance(node, ast.Constant) and node.value is None)


def _is_check_shaped(checks: ast.expr | None) -> bool:
    """Whether a mapping's entries are recognisably Pebble checks.

    Used where the surrounding mapping is not itself identifiable as a
    layer: the entries have to carry a check's own keys, or be built by
    the ``CheckDict`` typed-dict constructor, before a ``checks`` key is
    taken to mean Pebble's.
    """
    if not isinstance(checks, ast.Dict):
        return False
    return any(
        (isinstance(check, ast.Dict) and _CHECK_MARKERS.intersection(_ast.dict_keys(check)))
        or (isinstance(check, ast.Call) and _ast.dotted_name(check.func) == "CheckDict")
        for check in checks.values
    )


def _is_service_shaped(services: ast.expr | None) -> bool:
    """Whether a mapping's entries are recognisably Pebble services.

    The ``services`` counterpart of :func:`_is_check_shaped`, for a layer
    with no other key to give it away.
    """
    if not isinstance(services, ast.Dict):
        return False
    return any(
        (isinstance(service, ast.Dict) and _SERVICE_MARKERS.intersection(_ast.dict_keys(service)))
        or (isinstance(service, ast.Call) and _ast.dotted_name(service.func) == "ServiceDict")
        for service in services.values
    )


def _is_section(section: str, keys: set[str], value: ast.expr | None) -> bool:
    """Whether *value*, found under *section* beside *keys*, is a layer's section."""
    if _LAYER_MARKERS.intersection(keys - {section}):
        return True
    if section == _CHECKS:
        return _is_check_shaped(value)
    return _is_service_shaped(value)


def _sections(
    context: models.CharmContext, section: str
) -> Iterator[tuple[_Site, ast.expr | None]]:
    """Yield every place the charm's own source fills in a layer *section*.

    Layers reach Pebble as a dict literal, as keyword arguments to the
    ``LayerDict`` constructor, or as a YAML document in a string, so all
    three spellings are read. One assembled dynamically has no literal to
    inspect and is invisible here, which is a false negative rather than
    a false positive.

    The value is the expression the section was given, or ``None`` where
    it came from a YAML document and there is no expression to hand back.
    """
    for module in context.charm_sources():
        for node in module.walk(ast.Dict):
            value = _ast.dict_get(node, section)
            if _is_populated(value) and _is_section(section, set(_ast.dict_keys(node)), value):
                yield _Site(module.path, node.lineno), value
        for call in module.walk(ast.Call):
            value = _ast.keyword(call, section)
            keys = {kw.arg for kw in call.keywords if kw.arg}
            if _is_populated(value) and (
                _ast.dotted_name(call.func) in _LAYER_DICT or _is_section(section, keys, value)
            ):
                yield _Site(module.path, call.lineno), value
        for node in module.walk(ast.Constant, ast.JoinedStr):
            layer = _yaml_layer(node, section, module.path)
            entry = layer.get(section) if layer else None
            if entry and isinstance(entry.value, dict) and entry.value:
                yield _Site(module.path, entry.line or node.lineno), None


def _layer_sites(context: models.CharmContext) -> list[_Site]:
    """Return every Pebble layer the charm builds with services in it.

    Only a ``services`` mapping this module can read counts. A layer
    whose services come from somewhere else is a layer whose checks
    could come from there too.
    """
    return [
        site
        for site, value in _sections(context, _SERVICES)
        if value is None or isinstance(value, ast.Dict)
    ]


def _check_sites(context: models.CharmContext) -> list[_Site]:
    """Return every Pebble check definition the charm's source spells out."""
    return [
        site
        for site, value in _sections(context, _CHECKS)
        if value is None or isinstance(value, ast.Dict)
    ]


def _mentions_checks(context: models.CharmContext) -> bool:
    """Whether anything in the charm's source fills in a layer's checks.

    Looser than :func:`_check_sites`: a ``checks`` section handed a
    method call or a name bound elsewhere counts here, because the charm
    plainly has checks even though this module cannot read them.
    """
    return any(True for _ in _sections(context, _CHECKS))


def _watches_checks(context: models.CharmContext) -> bool:
    """Whether the charm does anything with its Pebble checks at runtime.

    Two shapes count. The charm may drive the checks itself, through the
    ``Container`` methods that only exist for them. Or it may hand them
    to a helper that watches them on its charm's behalf — cosl's
    ``StatusManager(block_if_pebble_checks_failing=...)`` is the common
    one — which a keyword argument naming Pebble checks gives away.

    Either way the charm has checks, and something is looking at them.
    """
    for module in context.charm_sources():
        for call in module.walk(ast.Call):
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr in _CHECK_METHODS
                and _may_be_container(call)
            ):
                return True
            if any(kw.arg and _CHECK_KEYWORD in kw.arg for kw in call.keywords):
                return True
    return False


def _may_be_container(call: ast.Call) -> bool:
    """Whether *call*'s receiver could be an ``ops.Container``.

    With no type information the receiver's name is all there is to go
    on. One that can't be read (``self.unit.get_container("web")``) may
    well be a container, and only suppresses a finding, so it counts.
    """
    name = _ast.receiver(call)
    if name is None:
        return True
    return any(hint in name.lower() for hint in ("container", "workload"))


def _observes_check_failed(context: models.CharmContext) -> bool:
    """Whether the charm observes ``<container>_pebble_check_failed``."""
    for module in context.charm_sources():
        for observer in _ast.observers(module):
            if observer.event is not None and observer.event.endswith(_CHECK_FAILED_SUFFIX):
                return True
    return False


def _has_unresolved_observer(context: models.CharmContext) -> bool:
    """Whether some observe call's event could not be read statically.

    A rule that reasons about an event *not* being observed has to treat
    one it could not decode as possibly being that event, or it reports
    on charms it merely failed to understand.
    """
    return any(
        not observer.resolved
        for module in context.charm_sources()
        for observer in _ast.observers(module)
    )


def _sets_on_check_failure(context: models.CharmContext) -> bool:
    """Whether a service hands its check failures to Pebble to act on.

    Unlike ``services`` and ``checks``, this one has no keyword spelling:
    the hyphen in ``on-check-failure`` is not a Python identifier, so a
    service written as keyword arguments still spells it as a mapping key.
    """
    for module in context.charm_sources():
        for node in module.walk(ast.Dict):
            if _is_populated(_ast.dict_get(node, _ON_CHECK_FAILURE)):
                return True
        for node in module.walk(ast.Constant, ast.JoinedStr):
            layer = _yaml_layer(node, _ON_CHECK_FAILURE, module.path)
            if layer and any(
                service.get(_ON_CHECK_FAILURE).value for _, service in layer.get(_SERVICES).items()
            ):
                return True
    return False


class MissingPebbleChecks(Rule):
    """Detect a Pebble layer whose services have no health checks.

    Scoped to a layer the charm builds in its own source: a workload
    whose plan comes from the rock, or from a helper library installed as
    a dependency, may well have checks this rule cannot see, so there is
    nothing to say about it.
    """

    category = "FEATURES"
    number = 2
    name = "missing-pebble-checks"
    description = "Pebble layer defines services but no health checks"
    default_severity = models.Severity.INFO
    reference_url = "https://ubuntu.com/docs/pebble/reference/health-checks/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.metadata.get("containers"):
            return []
        layers = _layer_sites(context)
        if not layers:
            return []
        if _mentions_checks(context) or _watches_checks(context):
            return []
        if _observes_check_failed(context):
            return []
        layer = layers[0]
        return [
            self.diagnostic(
                "Pebble layer defines services but no `checks:` — Juju has nothing to "
                "report the workload's health from, so a container whose process is "
                "running but not serving looks healthy",
                path=layer.path,
                line=layer.line,
                fix_hint=(
                    "Add a `checks:` section to the layer, with an `http`, `tcp` or "
                    "`exec` check per service"
                ),
            )
        ]


class UnhandledPebbleCheckFailure(Rule):
    """Detect Pebble checks that nothing responds to when they fail.

    The complement of :class:`MissingPebbleChecks`: this one fires only
    where that one does not, on a charm that went to the trouble of
    defining checks and then left the failure unhandled.
    """

    category = "FEATURES"
    number = 3
    name = "unhandled-pebble-check-failure"
    description = "Pebble check is defined but its failure is never handled"
    default_severity = models.Severity.WARNING
    reference_url = (
        "https://canonical.com/juju/docs/ops/latest/reference/ops/#ops.PebbleCheckFailedEvent"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.metadata.get("containers"):
            return []
        checks = _check_sites(context)
        if not checks:
            return []
        if _observes_check_failed(context) or _has_unresolved_observer(context):
            return []
        if _sets_on_check_failure(context) or _watches_checks(context):
            return []
        check = checks[0]
        return [
            self.diagnostic(
                "Pebble check is defined but the charm never observes "
                "`<container>_pebble_check_failed` and no service sets "
                "`on-check-failure` — a failing check leaves the workload broken "
                "with no status change and no restart",
                path=check.path,
                line=check.line,
                fix_hint=(
                    "Observe `self.on['<container>'].pebble_check_failed` and set a "
                    "status there, or give the service an `on-check-failure` entry so "
                    "Pebble restarts it"
                ),
            )
        ]


# `assumes` entries nest: a group is a single-key mapping whose value is
# the list of nested entries. Both quantifiers are valid at any depth.
_GROUP_KEYS = ("any-of", "all-of")


def _is_juju_entry(entry: models.Yaml) -> bool:
    """Report whether *entry* is a `juju` feature expression.

    Both structures mean the same thing to Juju: the flat string form
    (``juju >= 3.6``) and the mapping form (``{juju: ">= 3.6"}``). In
    either form, a bare ``juju`` with nothing after it is not a version
    constraint, so it does not count.
    """
    value = entry.value
    if isinstance(value, str):
        head, _, rest = value.strip().partition(" ")
        return head.lower() == "juju" and bool(rest.strip())
    if isinstance(value, dict):
        return any(
            isinstance(key, str)
            and key.strip().lower() == "juju"
            and isinstance(val, str)
            and bool(val.strip())
            for key, val in value.items()
        )
    return False


def _has_juju_constraint(assumes: models.Yaml) -> bool:
    """Report whether *assumes* declares a Juju version anywhere inside it.

    A charm may put the constraint inside an ``any-of`` / ``all-of``
    group rather than at the top level. Either way the charm has thought
    about the version, which is all this rule asks for.
    """
    for entry in assumes.elements or ():
        if _is_juju_entry(entry):
            return True
        for key in _GROUP_KEYS:
            if key in entry and _has_juju_constraint(entry.get(key)):
                return True
    return False


class NoAssumesJujuVersion(Rule):
    """Check that the charm declares the oldest Juju it supports.

    ``assumes`` is how a charm tells a controller what it needs. With a
    ``juju >= x.y`` entry, a controller too old to run the charm
    refuses the deploy and says so; without one, the charm deploys and
    then fails at whichever hook first reaches the feature it assumed,
    which is a much longer walk back to the cause.

    The constraint counts wherever it appears — nested inside an
    ``any-of`` or ``all-of`` group as readily as at the top level — and
    in either spelling Juju accepts, the flat ``juju >= 3.6`` and the
    mapping ``{juju: ">= 3.6"}``. A bare ``juju`` with no version after
    it constrains nothing and does not count.

    Only charms whose metadata lives in ``charmcraft.yaml`` are
    checked: one still declaring ``name`` in ``metadata.yaml`` predates
    the unified file, and may predate ``assumes`` (Juju 2.9.23)
    altogether. Bundles are skipped, having no ``assumes`` to declare.
    """

    category = "FEATURES"
    number = 4
    name = "no-assumes-juju-version"
    description = "No `assumes:` entry declaring a minimum Juju version"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-assumes"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # A bundle has no `assumes`; the key is charm metadata only.
        if context.metadata.get("type").value == "bundle":
            return []
        name = context.metadata.get("name")
        # Only charms that keep their metadata in charmcraft.yaml. A charm
        # still declaring `name` in metadata.yaml predates the unified
        # file, and possibly predates `assumes` (Juju 2.9.23) as well.
        if not name.present or name.source != "charmcraft.yaml":
            return []
        assumes = context.metadata.get("assumes")
        if _has_juju_constraint(assumes):
            return []
        return [
            self.diagnostic(
                "No `assumes:` entry declaring a minimum Juju version — Juju cannot "
                "refuse to deploy the charm onto a controller too old for it",
                # An `assumes` block that exists but says nothing about the
                # Juju version is worth pointing at; an absent one has no
                # line to anchor to.
                path=assumes.source if assumes.present else context.metadata.source,
                line=assumes.line,
                fix_hint=(
                    "Add `assumes: [juju >= 3.6]`, naming the oldest Juju the charm supports"
                ),
            )
        ]


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
_WORKLOAD_VERSION_SETTERS = frozenset({
    "coordinated_workers.worker",
    "cosl.coordinated_workers.worker",
})

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


_CONFIG_CHANGED = "config_changed"


class NoConfigChangedObserver(Rule):
    """Flag a charm that declares config options but never observes ``config-changed``.

    ``config-changed`` is the event Juju emits when an operator runs
    ``juju config``. A charm that declares options and never handles it
    picks the new values up at whatever event happens to fire next, which
    may be much later or never. From the Juju user's perspective, the
    setting was silently ignored.

    Handling it does not have to mean observing it, and the rule stays
    quiet wherever the charm might be dealing with configuration
    somewhere charmlint cannot see:

    * The charm's own source names ``<...>.on.config_changed`` anywhere:
      observed under an alias, listed for a holistic reconciler, or handed
      to a library as a refresh event.
    * An observe call could not be read statically, such as an event held
      in a variable or a helper that observes a list of events. It may be
      observing ``config-changed``.
    * No plain ``ops.CharmBase`` subclass was found in the charm's own
      source. The charm is either not an ops charm, built on a framework
      base class that observes on its behalf, or assembled somewhere the
      scan does not reach.
    * The charm reconciles unconditionally in ``__init__``, so it runs on
      every event including this one, or hands a callback to a
      collaborator that observes on its behalf.
    * The charm's source wires up no observers at all, which means
      something outside it does.
    * The charm's source never reads its own configuration, so the
      options belong to a library that reads (and observes) them.

    Two kinds of charm should suppress the rule with a ``file-ignore``
    comment in the file that declares their options: one whose options
    are only read when an action runs, so a change rightly waits for the
    next run, and one that applies its configuration outside ops
    altogether, such as in the entry point before it calls ``ops.main``.
    """

    category = "FEATURES"
    number = 7
    name = "no-config-changed-observer"
    description = "Charm declares config options but does not observe config-changed"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/ops/latest/howto/manage-configuration/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.config_options:
            return []
        charm_classes = 0
        observer_count = 0
        reads_config = False
        for module in context.charm_sources():
            if _mentions_config_changed(module) or _has_opaque_observe(module):
                return []
            classes = _classes(module)
            if classes.framework or classes.holistic:
                return []
            charm_classes += classes.plain
            reads_config = reads_config or _reads_config(module)
            for observer in _ast.observers(module):
                observer_count += 1
                if not observer.resolved or observer.event == _CONFIG_CHANGED:
                    return []
        if not charm_classes or not observer_count or not reads_config:
            return []
        return [
            self.diagnostic(
                "Charm declares config options but never handles 'config-changed', "
                "so operator configuration changes are silently ignored",
                path=context.config_options.source,
                line=context.config_options.line,
                fix_hint=(
                    "Add `framework.observe(self.on.config_changed, self._on_config_changed)` "
                    "in __init__ and a handler that reconciles the workload with the new "
                    "configuration"
                ),
            )
        ]


def _mentions_config_changed(module: models.Module) -> bool:
    """Whether *module* names the ``config-changed`` event at all.

    Charms reach the event by more routes than a literal
    ``framework.observe(self.on.config_changed, ...)``: through a local
    alias for ``observe``, through a list of events fed to a holistic
    reconciler, or by handing ``self.on.config_changed`` to a charm
    library as its ``refresh_event``. All of them write
    ``<...>.on.config_changed``.
    """
    return any(
        node.attr == _CONFIG_CHANGED
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "on"
        for node in module.walk(ast.Attribute)
    )


def _has_opaque_observe(module: models.Module) -> bool:
    """Whether *module* registers observers through something unreadable.

    ``observe_events(self, all_events, self._reconcile)``, a helper that
    loops over a list of events, registers ``config-changed`` without
    ever naming it. Any observe-shaped call that :func:`_ast.observers`
    could not decode is treated as possibly being one of those.
    """
    decoded = {id(observer.call) for observer in _ast.observers(module)}
    for call in module.walk(ast.Call):
        name = _called_name(call.func)
        if name is not None and name.startswith("observe") and id(call) not in decoded:
            return True
    return False


@dataclasses.dataclass
class _Classes:
    """What one module's class definitions say about the charm."""

    # Classes deriving straight from ``ops.CharmBase``: the ones whose
    # observers are all in the charm's own source.
    plain: int = 0
    # A charm class built on a framework base, or on a mixin alongside
    # ``ops.CharmBase``: it inherits observers charmlint cannot see.
    framework: bool = False
    # A charm class that reconciles unconditionally in ``__init__``, or
    # hands a callback to a collaborator that will observe for it.
    holistic: bool = False


def _classes(module: models.Module) -> _Classes:
    """Classify the charm classes *module* defines.

    Bases are resolved rather than pattern-matched, because a base named
    like ``ops.CharmBase`` may still observe on the charm's behalf
    (``single_kernel_kafka``'s ``ConnectCharmBase``, for one).
    """
    imports = _ast.Imports.of(module)
    entry_points = _main_arguments(module, imports)
    result = _Classes()
    for node in module.walk(ast.ClassDef):
        bases = {name for name in (imports.resolve(base) for base in node.bases) if name}
        ops_bases = bases & _ast.CHARM_BASES
        if ops_bases and not bases - ops_bases:
            result.plain += 1
            result.holistic = (
                result.holistic or _reconciles_in_init(node) or _delegates_to_collaborator(node)
            )
        elif ops_bases or node.name in entry_points:
            # Either a mixin alongside ``ops.CharmBase``, or a charm class
            # whose base is something charmlint cannot see into.
            result.framework = True
    return result


def _main_arguments(module: models.Module, imports: _ast.Imports) -> set[str]:
    """Return the names handed to ``ops.main(...)`` in *module*."""
    names: set[str] = set()
    for call in module.walk(ast.Call):
        if _ast.call_target(call, imports) not in _ast.OPS_MAIN_TARGETS or not call.args:
            continue
        name = _ast.dotted_name(call.args[0])
        if name is not None:
            names.add(name)
    return names


def _reconciles_in_init(node: ast.ClassDef) -> bool:
    """Whether *node*'s ``__init__`` does work rather than only wiring up.

    A statement-level ``self._reconcile()`` in ``__init__`` runs on every
    event the charm is dispatched for, ``config-changed`` included, so the
    charm handles configuration changes without observing anything.

    Only a bare call *statement* counts. Calls that build the charm's
    collaborators are expressions inside an assignment, and reading a
    property is not a call at all.
    """
    for function in node.body:
        if not isinstance(function, ast.FunctionDef) or function.name != "__init__":
            continue
        for statement in function.body:
            if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                continue
            if _is_self_attribute(statement.value.func):
                return True
    return False


def _is_self_attribute(node: ast.expr) -> bool:
    """Whether *node* is ``self.<name>``, a method or property of the charm."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _delegates_to_collaborator(node: ast.ClassDef) -> bool:
    """Whether *node*'s ``__init__`` hands one of its own methods to a helper.

    ``Reconciler(self, self.reconcile)``, the ``ops.manifests`` pattern
    the charmed-kubernetes charms are built on, passes the charm and a
    callback to an object that then observes the charm's events itself.
    Plenty of charm libraries take a bare ``self`` too, so only a call
    passing both the charm and a ``self.<name>`` reference counts.
    """
    for function in node.body:
        if not isinstance(function, ast.FunctionDef) or function.name != "__init__":
            continue
        for call in ast.walk(function):
            if not isinstance(call, ast.Call):
                continue
            arguments = [*call.args, *(kw.value for kw in call.keywords)]
            passes_self = any(isinstance(a, ast.Name) and a.id == "self" for a in arguments)
            if passes_self and any(_is_self_attribute(a) for a in arguments):
                return True
    return False


def _reads_config(module: models.Module) -> bool:
    """Whether *module* reads the charm's configuration itself.

    ``self.config``, ``self.charm.config`` and ``charm.model.config`` are
    all an attribute named ``config``. A charm that declares options but
    never touches them in its own source has handed them to a library
    (``cosl``'s ``Worker`` reads a worker's ``role-*`` options, and
    observes ``config-changed`` to do it), and that library's own
    observers are not visible here.
    """
    return any(node.attr == "config" for node in module.walk(ast.Attribute))
