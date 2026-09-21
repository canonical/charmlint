"""Features rules — capabilities a charm is expected to have but often lacks.

Some of these read what the charm tells Juju it needs, and some read
what its Python does with the workload: a charm that never gives Pebble
a health check, or never listens for one failing, has the same kind of
gap as one that never says which Juju it needs.
"""

import ast
import dataclasses
from collections.abc import Iterator

import yaml

from .. import _ast
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

# Keys that mark the mapping holding a ``checks`` entry as a Pebble
# layer. Without one, ``checks`` on its own is far too common a word to
# take a dict that has it for a layer.
_LAYER_MARKERS = frozenset({_SERVICES, "summary", "description"})

# Keys that only a Pebble check carries. They identify checks written
# away from the layer that will hold them — added to a container on their
# own, or built up in a local before the layer is assembled.
_CHECK_MARKERS = frozenset(
    {"override", "level", "period", "timeout", "threshold", "http", "tcp", "exec"}
)

# The Container methods that only make sense on a workload with checks.
# A charm that reads or drives its checks at runtime plainly has them,
# wherever they were defined.
_CHECK_METHODS = frozenset({"get_check", "get_checks", "start_checks", "stop_checks"})

# A keyword argument whose name mentions Pebble checks hands them to a
# helper that watches them on the charm's behalf.
_CHECK_KEYWORD = "pebble_check"

# The event ops emits when a Pebble check crosses its failure threshold,
# spelled ``<container>_pebble_check_failed``.
_CHECK_FAILED_SUFFIX = "_pebble_check_failed"

# The layer key that hands the failure to Pebble instead: a service that
# names a check under ``on-check-failure`` is restarted by Pebble when
# the check fails, which is a real response to the failure.
_ON_CHECK_FAILURE = "on-check-failure"

# Stands in for an interpolated expression when reading an f-string layer
# as YAML. The value is never inspected — only the shape of the document
# around it matters.
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


def _yaml_layer(node: ast.Constant | ast.JoinedStr, section: str) -> dict | None:
    """Return a string literal parsed as a layer document, else ``None``.

    Only a string that names *section* is worth handing to the parser, and
    one that does not parse — a fragment, or a template whose placeholders
    broke the indentation — is not a layer that can be read.
    """
    text = _string_text(node)
    if text is None or f"{section}:" not in text:
        return None
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return loaded if isinstance(loaded, dict) else None


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
            if _is_populated(value) and (
                _LAYER_MARKERS.intersection(_ast.dict_keys(node)) or _is_check_shaped(value)
            ):
                yield _Site(module.path, node.lineno), value
        for call in module.walk(ast.Call):
            value = _ast.keyword(call, section)
            if _is_populated(value):
                yield _Site(module.path, call.lineno), value
        for node in module.walk(ast.Constant, ast.JoinedStr):
            layer = _yaml_layer(node, section)
            if layer and isinstance(layer.get(section), dict) and layer[section]:
                yield _Site(module.path, node.lineno), None


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
            if isinstance(call.func, ast.Attribute) and call.func.attr in _CHECK_METHODS:
                return True
            if any(kw.arg and _CHECK_KEYWORD in kw.arg for kw in call.keywords):
                return True
    return False


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
            services = (_yaml_layer(node, _ON_CHECK_FAILURE) or {}).get(_SERVICES)
            if isinstance(services, dict) and any(
                isinstance(service, dict) and service.get(_ON_CHECK_FAILURE)
                for service in services.values()
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
    reference_url = "https://documentation.ubuntu.com/pebble/reference/health-checks/"

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
        "https://documentation.ubuntu.com/ops/latest/reference/ops/#ops.PebbleCheckFailedEvent"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
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
