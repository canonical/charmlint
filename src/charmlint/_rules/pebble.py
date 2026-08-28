"""Pebble rules — layer definitions built in the charm's Python source."""

import ast
import pathlib

from .. import _models as models
from ._base import Rule


def _constant_key(key: ast.expr | None) -> str | None:
    """Return the string key of a dict entry, or ``None``.

    ``key`` is ``None`` for a ``**unpacking`` entry, which has no key at
    all; a computed key is an expression we can't resolve statically.
    """
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    return None


def _lookup(node: ast.Dict, name: str) -> ast.expr | None:
    """Return the value of *node*'s ``name`` entry, or ``None``."""
    for key, value in zip(node.keys, node.values, strict=True):
        if _constant_key(key) == name:
            return value
    return None


def _keys(node: ast.Dict) -> set[str]:
    """Return the string keys of a dict literal."""
    return {key for key in (_constant_key(k) for k in node.keys) if key is not None}


# Keys that only a Pebble service dict carries. A layer's services are
# often built a step at a time — the service dict assigned to a local
# and then dropped into ``{"services": {name: <local>}}`` — so a service
# is also recognised on its own, away from the layer that will hold it.
#
# ``command`` also matches the inner dict of an exec check, which is
# deliberate: a check's ``environment`` is the same ``map[string]string``
# as a service's, so the same coercion trap applies to it.
_SERVICE_MARKERS = frozenset({"override", "command"})


def _environment_dicts(tree: ast.AST) -> list[ast.Dict]:
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
        environment = _lookup(service, "environment")
        if isinstance(environment, ast.Dict) and id(environment) not in seen:
            seen.add(id(environment))
            found.append(environment)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        services = _lookup(node, "services")
        if isinstance(services, ast.Dict):
            for service in services.values:
                add(service)
        if _SERVICE_MARKERS.intersection(_keys(node)):
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
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for environment in _environment_dicts(tree):
                diagnostics.extend(self._check_environment(environment, path))
        return diagnostics

    def _check_environment(
        self, environment: ast.Dict, path: pathlib.Path
    ) -> list[models.Diagnostic]:
        """Report every non-string constant value in one ``environment`` dict."""
        diagnostics: list[models.Diagnostic] = []
        for key, value in zip(environment.keys, environment.values, strict=True):
            if not isinstance(value, ast.Constant) or isinstance(value.value, str):
                continue
            name = _constant_key(key)
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
                    path=str(path),
                    line=value.lineno,
                    fix_hint=fix_hint,
                )
            )
        return diagnostics
