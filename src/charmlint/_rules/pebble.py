"""Pebble rules — layer definitions built in the charm's Python source."""

import ast

from .. import _ast, _yaml
from .. import _models as models
from ._base import Rule

# Keys that only a Pebble service dict carries. A layer's services are
# often built a step at a time — the service dict assigned to a local
# and then dropped into ``{"services": {name: <local>}}`` — so a service
# is also recognised on its own, away from the layer that will hold it.
#
# ``command`` also matches the inner dict of an exec check, which is
# deliberate: a check's ``environment`` is the same ``map[string]string``
# as a service's, so the same coercion trap applies to it.
_SERVICE_MARKERS = frozenset({"override", "command"})


def _environment_dicts(module: models.Module) -> list[ast.Dict]:
    """Return every ``environment`` dict literal of a Pebble service or check.

    Layers are ordinary dict literals in charm source — passed to
    ``ops.pebble.Layer(...)``, to ``container.add_layer(...)``, or
    returned from a ``_pebble_layer`` property — so match on the shape
    rather than on the call that consumes it: a service nested under a
    ``services`` mapping, or a dict that carries a Pebble service key
    alongside its ``environment``. Anything built dynamically (an
    environment assembled from variables, or read from YAML) has no dict
    literal to walk and is silently skipped.
    """
    found: list[ast.Dict] = []
    seen: set[int] = set()

    def add(service: ast.expr | None) -> None:
        if not isinstance(service, ast.Dict):
            return
        environment = _ast.dict_get(service, "environment")
        if isinstance(environment, ast.Dict) and id(environment) not in seen:
            seen.add(id(environment))
            found.append(environment)

    for node in module.walk(ast.Dict):
        services = _ast.dict_get(node, "services")
        if isinstance(services, ast.Dict):
            for service in services.values:
                add(service)
        if _SERVICE_MARKERS.intersection(_ast.dict_keys(node)):
            add(node)
    return found


class PebbleEnvNonString(Rule):
    """Detect non-string literals in a Pebble layer's service ``environment``.

    Only constant values are flagged. A value built by ``str(...)``, an
    f-string, or any other expression is left alone: the rule can't tell
    what it evaluates to, and the common cases are already strings.
    """

    category = "PEBBLE"
    number = 5
    name = "pebble-env-non-string"
    description = "Pebble layer environment value is not a string"
    default_severity = models.Severity.INFO
    reference_url = "https://ubuntu.com/docs/pebble/reference/layer-specification/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            for environment in _environment_dicts(module):
                diagnostics.extend(self._check_environment(environment, module.path))
        return diagnostics

    def _check_environment(self, environment: ast.Dict, path: str) -> list[models.Diagnostic]:
        """Report every non-string constant value in one ``environment`` dict."""
        diagnostics: list[models.Diagnostic] = []
        for key, value in zip(environment.keys, environment.values, strict=True):
            if not isinstance(value, ast.Constant) or isinstance(value.value, str):
                continue
            name = _ast.dict_key(key)
            described = f"'{name}'" if name is not None else "an environment variable"
            severity: models.Severity | None = None
            if value.value is None:
                message = (
                    f"Pebble layer environment value for {described} is None "
                    f"— Pebble rejects the whole layer at runtime"
                )
                severity = models.Severity.ERROR
                fix_hint = "Use a string, or omit the variable when it has no value"
            elif isinstance(value.value, bool):
                # bool is a subclass of int, so it has to be tested first.
                literal = str(value.value)
                message = (
                    f"Pebble layer environment value for {described} is a bool "
                    f"— it serialises as '{literal}', where workloads usually "
                    f"expect '{literal.lower()}' or '{int(value.value)}'"
                )
                fix_hint = f"Write the value the workload expects, e.g. '{literal.lower()}'"
            else:
                message = (
                    f"Pebble layer environment value for {described} is not a string "
                    f"— Pebble coerces it, but the coerced form is easy to get wrong"
                )
                fix_hint = f"Use a string literal, e.g. '{value.value}'"
            diagnostics.append(
                self.diagnostic(
                    message,
                    severity=severity,
                    path=path,
                    line=value.lineno,
                    fix_hint=fix_hint,
                )
            )
        return diagnostics


class PebbleCheckLevelAlive(Rule):
    """Detect a Pebble check with ``level: alive`` in a layer built in charm source.

    Juju points the sidecar container's Kubernetes liveness probe at
    Pebble's ``/v1/health?level=alive``, so once an ``alive`` check is down
    Kubernetes restarts the whole container, rather than Pebble or the
    charm restarting the service. A workload that is slow to start, or
    briefly unhealthy during an upgrade, ends up in a restart loop. Use a
    check with no ``level`` and ``on-check-failure`` on the service instead.

    A check is recognised by its shape: a dict literal, or a call such as
    ``CheckDict(...)`` or ``dict(...)`` with keyword arguments, that has a
    ``level`` of ``"alive"`` (or ``ops.pebble.CheckLevel.ALIVE``) alongside
    an ``http``, ``tcp`` or ``exec`` key, or a check under ``checks`` in a
    layer written as a YAML string passed to ``ops.pebble.Layer`` or
    ``add_layer``. A level computed at runtime is left alone, as is a
    layer read from a YAML file. A fast-starting
    workload whose author really does want Kubernetes to restart the
    container can suppress the rule on that line.
    """

    category = "PEBBLE"
    number = 6
    name = "pebble-check-level-alive"
    description = "Pebble check uses level 'alive', which drives the Kubernetes liveness probe"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/ops/latest/howto/manage-containers/manage-pebble-health-checks/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            imports = _ast.Imports.of(module)
            lines = [level.lineno for level in _check_levels(module) if _is_alive(level, imports)]
            lines.extend(_yaml_alive_lines(module, imports))
            for line in sorted(lines):
                diagnostics.append(
                    self.diagnostic(
                        "Pebble check has level 'alive', so Kubernetes restarts the "
                        "whole container when the check is down",
                        path=module.path,
                        line=line,
                        fix_hint=(
                            "Drop the level and set `on-check-failure` on the service, "
                            "so Pebble restarts the service instead"
                        ),
                    )
                )
        return diagnostics


# Keys only a Pebble check carries: the three kinds of check.
_CHECK_MARKERS = frozenset({"http", "tcp", "exec"})


def _check_levels(module: models.Module) -> list[ast.expr]:
    """Return the ``level`` of every dict literal or keyword call shaped like a Pebble check.

    As with services, a check is often built a step at a time, with the
    kind added later or arriving through ``**``, so a dict nested under a
    ``checks`` mapping counts as a check even without ``http``, ``tcp`` or
    ``exec``. So does a dict on its own that carries one of those, or that
    has both ``override`` and ``level``, which only a check does.
    """
    levels: list[ast.expr] = []
    seen: set[int] = set()

    def add(check: ast.expr) -> None:
        if not isinstance(check, ast.Dict) or id(check) in seen:
            return
        seen.add(id(check))
        level = _ast.dict_get(check, "level")
        if level is not None:
            levels.append(level)

    for node in module.walk(ast.Dict, ast.Call):
        if isinstance(node, ast.Dict):
            checks = _ast.dict_get(node, "checks")
            if isinstance(checks, ast.Dict):
                for check in checks.values:
                    add(check)
            keys = _ast.dict_keys(node)
            if _CHECK_MARKERS & keys or {"override", "level"} <= keys:
                add(node)
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        if _CHECK_MARKERS & keywords.keys() and "level" in keywords:
            levels.append(keywords["level"])
    return levels


def _yaml_alive_lines(module: models.Module, imports: _ast.Imports) -> list[int]:
    """Return the source line of each ``level: alive`` in a layer written as a YAML string.

    The string is the first argument to ``ops.pebble.Layer(...)``, or the
    second to ``<anything>.add_layer(label, ...)``, either positional or as
    the ``raw``/``layer`` keyword. A line in the string is offset from the
    line the string starts on, so a ``# noqa`` on the ``level`` line works.
    """
    lines: list[int] = []
    for call in module.walk(ast.Call):
        if _ast.call_target(call, imports) == "ops.pebble.Layer":
            raw = call.args[0] if call.args else _ast.keyword(call, "raw")
        elif isinstance(call.func, ast.Attribute) and call.func.attr == "add_layer":
            raw = call.args[1] if len(call.args) > 1 else _ast.keyword(call, "layer")
        else:
            continue
        if not isinstance(raw, ast.Constant) or not isinstance(raw.value, str):
            continue
        layer = _yaml.loads(raw.value, module.path)
        if layer is None:
            continue
        for _, check in layer.get("checks").items():
            level = check.get("level")
            if level.value == "alive" and level.line is not None:
                lines.append(raw.lineno + level.line - 1)
    return lines


def _is_alive(level: ast.expr, imports: _ast.Imports) -> bool:
    """Whether *level* is the ``alive`` check level, as a string or the enum."""
    if isinstance(level, ast.Constant):
        return level.value == "alive"
    # ``CheckLevel("alive")`` is the enum built from its value.
    if isinstance(level, ast.Call) and _ast.call_target(level, imports) == "ops.pebble.CheckLevel":
        arg = level.args[0] if level.args else _ast.keyword(level, "value")
        return isinstance(arg, ast.Constant) and arg.value == "alive"
    # ``CheckLevel.ALIVE.value`` is the same thing spelled the long way.
    if isinstance(level, ast.Attribute) and level.attr == "value":
        level = level.value
    return imports.resolve(level) == "ops.pebble.CheckLevel.ALIVE"
