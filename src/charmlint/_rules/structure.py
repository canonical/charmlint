"""Structure rules — charm directory structure and required files."""

import ast
import pathlib

from .. import _models as models
from ._base import Rule


def _is_valid_licence(path: pathlib.Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


class NoLicence(Rule):
    """Check that the charm ships a licence file.

    Charm source is published for people to read, fork and fix, and
    without a licence file none of them know on what terms they may.

    ``LICENSE`` and ``LICENCE`` are both accepted, but only at the
    charm root and only spelled in upper case — a ``COPYING``, a
    ``LICENSE.txt``, or a licence kept under ``docs/`` is not
    recognised. An empty file is not a licence either. Shipping *both*
    spellings is reported in its own right: two files invite the two
    drifting apart, and leave a reader guessing which one governs.
    """

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
    """Check that the charm ships an ``icon.svg``.

    The icon is how the charm is recognised on Charmhub; a charm
    without one is shown under a placeholder, alongside every other
    charm that skipped it.

    The file has to be at the charm root, named exactly ``icon.svg``,
    and non-empty — a zero-byte placeholder is reported as though it
    were missing. Nothing inside the SVG is examined: dimensions and
    viewBox are charmcraft's business, not this rule's.
    """

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


class NoTypeAnnotations(Rule):
    """Check that the charm's own source uses type annotations at all.

    Annotations are what let a type checker catch a wrong event type, a
    misspelt attribute or a ``None`` that was never handled before the
    charm is deployed. A charm with none at all gets no help from one.

    The rule reports once per charm, not per function: annotating every
    local is not the convention, and a rule that demanded it would fire
    on almost every charm. Any annotation anywhere — a return type, a
    parameter, or an annotated assignment — is enough to pass. Only the
    charm's own source counts: ``src/`` plus any library the charm
    publishes, never a vendored copy of someone else's library, and never
    the tests. A charm with no functions has nothing to annotate and is
    not reported.
    """

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
