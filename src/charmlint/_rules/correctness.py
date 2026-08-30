"""Correctness rules — charm code that cannot do what it says at runtime."""

import ast

from .. import _ast as ast_helpers
from .. import _models as models
from ._base import Rule

_GET_CONTAINER = "get_container"
_NAME_KEYWORD = "container_name"


def _container_name(call: ast.Call) -> ast.Constant | None:
    """Return the string-literal name a ``get_container`` call asks for.

    ``None`` for a name this rule cannot read: a variable, an f-string, a
    lookup into ``self.meta.containers``. Those are the spellings that
    *cannot* be checked against the declared names, and they are also the
    spellings that are usually right, so leaving them alone costs little.
    """
    argument = call.args[0] if call.args else ast_helpers.keyword(call, _NAME_KEYWORD)
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument
    return None


def _get_container_names(module: models.Module) -> list[ast.Constant]:
    """Return the name node of each ``get_container("name")`` call in *module*.

    Matched on the method name alone. ``get_container`` is
    ``ops.Unit.get_container`` in practice — charmlint has no type
    inference, so a same-named method on an unrelated object would match
    too, but no such method is in common use in charms.
    """
    found: list[ast.Constant] = []
    for call in module.walk(ast.Call):
        if not isinstance(call.func, ast.Attribute) or call.func.attr != _GET_CONTAINER:
            continue
        name = _container_name(call)
        if name is not None:
            found.append(name)
    return found


class ContainerNameMismatch(Rule):
    """Detect ``get_container()`` calls naming an undeclared container.

    A container name that isn't declared under ``containers:`` raises
    ``ops.ModelError`` the first time the hook runs, and the classic way
    to get there is to assume the container is named after the app.

    Only the charm's own ``src/`` is checked. A library the charm
    publishes is written to run inside *other* charms, so a container
    name there refers to a container this charm's metadata has no reason
    to declare.

    Nothing is reported unless the charm declares at least one container
    of its own, and nothing at all is reported for a charm using a
    charmcraft ``extensions:`` profile. Both are cases where the
    containers charmcraft ends up building are not the containers
    charmlint can read: a ``go-framework`` charm's ``app`` container is
    injected by the extension, and a charm whose metadata is generated
    (from a ``metadata.yaml.j2``, say) declares its containers somewhere
    charmlint never sees. Reporting those means reporting a charm we
    failed to understand.
    """

    category = "CORRECTNESS"
    number = 9
    name = "container-name-mismatch"
    description = "get_container() names a container not declared in containers:"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-containers"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if context.metadata.get("extensions"):
            return []
        containers = context.metadata.get("containers")
        declared = {str(name) for name in containers}
        if not declared:
            return []
        diagnostics: list[models.Diagnostic] = []
        for module in context.modules(models.Scope.SRC):
            for name in _get_container_names(module):
                if name.value in declared:
                    continue
                known = ", ".join(f"'{c}'" for c in sorted(declared))
                diagnostics.append(
                    self.diagnostic(
                        f"get_container('{name.value}') does not match a container "
                        f"declared in {containers.source} — declared: {known}",
                        path=module.path,
                        line=name.lineno,
                        fix_hint=(
                            f"Use one of the declared names, or add '{name.value}' "
                            f"to 'containers:'"
                        ),
                    )
                )
        return diagnostics
