"""Structure rules — charm directory structure and required files."""

import ast
import pathlib

from .. import _models as models
from ._base import Rule


def _is_valid_licence(path: pathlib.Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


class NoLicence(Rule):
    category = "STRUCTURE"
    number = 1
    name = "no-licence"
    description = "No LICENSE/LICENCE file found"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # LICENSE (US) and LICENCE (UK) are both accepted.
        valid = [
            name for name in ("LICENSE", "LICENCE") if _is_valid_licence(context.charm_dir / name)
        ]
        if not valid:
            return [self.diagnostic(self.description)]
        if len(valid) == 2:
            return [self.diagnostic("Both LICENSE and LICENCE files present; keep only one.")]
        return []


class NoIcon(Rule):
    category = "STRUCTURE"
    number = 2
    name = "no-icon"
    description = "No icon.svg found"
    default_severity = models.Severity.INFO
    reference_url = (
        "https://canonical.com/juju/docs/charmcraft/stable/reference/files/icon-svg-file/"
    )

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        icon = context.charm_dir / "icon.svg"
        if not icon.is_file() or icon.stat().st_size == 0:
            return [self.diagnostic(self.description)]
        return []


def _uses_annotations(module: models.Module) -> bool:
    """Whether *module* carries a type annotation anywhere.

    Any annotation counts — an annotated return, an annotated parameter, or
    an annotated assignment. The rule asks whether the charm uses type hints
    at all, not whether it annotates everything, so a charm that annotates
    parameters but not returns has plainly answered the question.
    """
    for node in module.walk(ast.AnnAssign, ast.FunctionDef, ast.AsyncFunctionDef):
        if isinstance(node, ast.AnnAssign):
            return True
        if node.returns is not None:
            return True
        arguments = node.args
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            arguments.vararg,
            arguments.kwarg,
        ):
            if argument is not None and argument.annotation is not None:
                return True
    return False


class NoTypeAnnotations(Rule):
    category = "STRUCTURE"
    number = 3
    name = "no-type-annotations"
    description = "No type annotations found in charm source"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Charm-level, not per-function: annotating every local is not the
        # convention, and a rule that demanded it would fire on almost every
        # charm. This one fires only when the charm's own source — src/ plus
        # any library it publishes, never a vendored copy of someone else's —
        # has no annotation anywhere at all.
        sources = list(context.charm_sources())
        if not any(True for module in sources for _ in module.functions()):
            # No charm code, or no functions in it: nothing to annotate, so
            # the rule has nothing to say.
            return []
        if any(_uses_annotations(module) for module in sources):
            return []
        return [
            self.diagnostic(
                self.description,
                fix_hint="Annotate function parameters and return types, and run a type checker.",
            )
        ]
