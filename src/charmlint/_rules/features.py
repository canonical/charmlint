"""Feature rules — expected charm features that are commonly missing."""

from typing import Any

from .. import models
from . import Rule


def _requires_loki_push_api(metadata: dict[str, Any]) -> bool:
    """True if ``metadata['requires']`` has any entry with ``interface: loki_push_api``."""
    requires = metadata.get("requires")
    if not isinstance(requires, dict):
        return False
    for rel_def in requires.values():
        if isinstance(rel_def, dict) and rel_def.get("interface") == "loki_push_api":
            return True
    return False


class NoLogForwarderInstantiation(Rule):
    """Flag charms that declare a ``loki_push_api`` requires relation but never instantiate
    a ``LogForwarder`` or ``LogProxyConsumer`` helper.

    Pairs with COS003 (which fires when the relation is missing entirely): this rule
    only fires when the relation is declared but the helper isn't instantiated.
    """

    id = "FEAT007"
    name = "no-log-forwarder-instantiation"
    description = (
        "Charm declares loki_push_api requires relation but does not instantiate "
        "LogForwarder or LogProxyConsumer"
    )
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not _requires_loki_push_api(context.metadata):
            return []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            if "LogForwarder(" in content or "LogProxyConsumer(" in content:
                return []
        return [
            self.diagnostic(
                "Charm declares a `loki_push_api` requires relation but never "
                "instantiates `LogForwarder(...)` or `LogProxyConsumer(...)` — "
                "logs from the workload will not be forwarded to Loki",
                fix_hint=(
                    "Instantiate `LogForwarder(self, ...)` (or `LogProxyConsumer(self, ...)`) "
                    "in `__init__` so the loki_push_api relation actually forwards logs"
                ),
            )
        ]
