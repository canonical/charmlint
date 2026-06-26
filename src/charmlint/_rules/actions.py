"""Action rules — expected operational actions and action quality.

ACT001–ACT003 (expected actions) live here; ACT004–ACT007 return in
their own PRs.
"""

from .. import _models as models
from . import Rule

# Expected operational actions with their aliases.
_EXPECTED_ACTIONS: dict[str, tuple[str, list[str]]] = {
    "ACT001": (
        "get-health",
        ["health-check", "check-health", "get-status", "health"],
    ),
    "ACT002": (
        "pause",
        ["stop", "disable"],
    ),
    "ACT003": (
        "resume",
        ["start", "enable"],
    ),
}


def _make_action_rule(_id: str, _canonical: str, _aliases: list[str]) -> type[Rule]:
    """Create a Rule subclass for a missing expected action."""
    rid, canonical, aliases = _id, _canonical, _aliases
    all_names = [canonical, *aliases]

    class _ActionRule(Rule):
        id = rid
        name = f"missing-{canonical}-action"
        description = f"Missing '{canonical}' action (or alias)"
        default_severity = models.Severity.WARNING

        def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
            action_names = set(context.actions.keys())
            if any(n in action_names for n in all_names):
                return []
            return [
                self.diagnostic(
                    f"Missing '{canonical}' action (or alias: {', '.join(aliases)})",
                    path="charmcraft.yaml",
                    fix_hint=f"Add a '{canonical}' action to charmcraft.yaml",
                )
            ]

    _ActionRule.__name__ = f"ActionRule_{rid}"
    _ActionRule.__qualname__ = _ActionRule.__name__
    return _ActionRule


for _rid, (_canonical, _aliases) in _EXPECTED_ACTIONS.items():
    _make_action_rule(_rid, _canonical, _aliases)
