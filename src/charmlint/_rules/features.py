"""Feature rules — expected charm features that are commonly missing."""

import ast

from .. import models
from . import Rule


def _is_charm_source(tree: ast.AST) -> bool:
    """True if the module defines an ``ops.CharmBase`` subclass or calls ``ops.main(...)``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if _is_charmbase_ref(base):
                    return True
        elif isinstance(node, ast.Call) and _is_ops_main(node.func):
            return True
    return False


def _is_charmbase_ref(node: ast.AST) -> bool:
    """True for ``CharmBase`` or ``ops.CharmBase`` (or any ``*.CharmBase``)."""
    if isinstance(node, ast.Name) and node.id == "CharmBase":
        return True
    return isinstance(node, ast.Attribute) and node.attr == "CharmBase"


def _is_ops_main(node: ast.AST) -> bool:
    """True for ``ops.main(...)`` used as a call target."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "main"
        and isinstance(node.value, ast.Name)
        and node.value.id == "ops"
    )


def _observe_event_name(call: ast.Call) -> str | None:
    """If ``call`` is a ``framework.observe(<event>, ...)``, return the trailing event attribute name.

    For example, ``self.framework.observe(self.on.upgrade_series_prepare, handler)``
    returns ``"upgrade_series_prepare"``.
    """
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "observe"):
        return None
    if not call.args:
        return None
    event = call.args[0]
    if isinstance(event, ast.Attribute):
        return event.attr
    return None


def _is_machine_charm(metadata: dict) -> bool:
    """True if charmcraft.yaml/metadata.yaml has no non-empty ``containers:`` key."""
    containers = metadata.get("containers")
    return not containers


class NoUpgradeSeriesHandler(Rule):
    """Flag machine charms that do not observe both upgrade-series events."""

    id = "FEAT009"
    name = "no-upgrade-series-handler"
    description = "Machine charm does not observe upgrade-series-prepare/upgrade-series-complete"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not _is_machine_charm(context.metadata):
            return []

        is_charm = False
        observes_prepare = False
        observes_complete = False
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            if not is_charm and _is_charm_source(tree):
                is_charm = True
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _observe_event_name(node)
                if name == "upgrade_series_prepare":
                    observes_prepare = True
                elif name == "upgrade_series_complete":
                    observes_complete = True

        if not is_charm:
            return []
        if observes_prepare and observes_complete:
            return []

        missing = []
        if not observes_prepare:
            missing.append("upgrade_series_prepare")
        if not observes_complete:
            missing.append("upgrade_series_complete")
        missing_str = " and ".join(f"`self.on.{m}`" for m in missing)
        return [
            self.diagnostic(
                f"Machine charm does not observe {missing_str} — operators cannot "
                "safely pause/resume the workload during a series upgrade",
                fix_hint=(
                    "Observe both `self.on.upgrade_series_prepare` and "
                    "`self.on.upgrade_series_complete` in __init__ and implement handlers "
                    "that stop/start the workload around the series upgrade"
                ),
            )
        ]
