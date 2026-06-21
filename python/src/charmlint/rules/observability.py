"""Observability rules — COS relations and ops-tracing."""

import re
from typing import Any

from .. import models
from . import Rule

# COS relation interface checks.
# First element is the interface *value* (not the relation name).
_COS_CHECKS: list[tuple[str, str, str, str]] = [
    (
        "tracing",
        "COS001",
        "missing-tracing-relation",
        "Missing tracing relation (interface: tracing)",
    ),
    (
        "prometheus_scrape",
        "COS002",
        "missing-metrics-endpoint",
        "Missing metrics-endpoint relation (interface: prometheus_scrape)",
    ),
    (
        "loki_push_api",
        "COS003",
        "missing-logging-relation",
        "Missing logging relation (interface: loki_push_api)",
    ),
    (
        "grafana_dashboard",
        "COS004",
        "missing-grafana-dashboard",
        "Missing grafana-dashboard relation (interface: grafana_dashboard)",
    ),
]


def _all_relation_interfaces(metadata: dict[str, Any]) -> set[str]:
    """Collect all relation interface names from metadata."""
    interfaces: set[str] = set()
    for section in ("requires", "provides", "peers"):
        for rel_def in metadata.get(section, {}).values():
            if isinstance(rel_def, dict) and rel_def.get("interface"):
                interfaces.add(rel_def["interface"])
    return interfaces


def _make_cos_rule(_iface: str, _id: str, _name: str, _msg: str) -> type[Rule]:
    """Dynamically create a Rule subclass for a COS relation check."""
    iface, rid, rname, msg = _iface, _id, _name, _msg

    class _CosRule(Rule):
        id = rid
        name = rname
        description = msg
        default_severity = models.Severity.WARNING

        def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
            interfaces = _all_relation_interfaces(context.metadata)
            if iface not in interfaces:
                return [self.diagnostic(msg, path="charmcraft.yaml")]
            return []

    _CosRule.__name__ = f"CosRule_{rid}"
    _CosRule.__qualname__ = _CosRule.__name__
    return _CosRule


for _interface, _rule_id, _name, _message in _COS_CHECKS:
    _make_cos_rule(_interface, _rule_id, _name, _message)


class OpsTracingNotInstalled(Rule):
    """Check that ops-tracing is listed as a dependency."""

    id = "COS005"
    name = "ops-tracing-not-installed"
    description = "ops-tracing not detected in dependencies or source"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Check requirements files.
        for req_name in ("requirements.txt", "pyproject.toml"):
            req_path = context.charm_dir / req_name
            if req_path.exists():
                try:
                    content = req_path.read_text(errors="replace")
                    if "ops-tracing" in content:
                        return []
                except OSError:
                    pass

        # Check source for setup call.
        for content in context.python_sources.values():
            if re.search(r"ops_tracing|setup_tracing", content):
                return []

        return [
            self.diagnostic(
                "ops-tracing not detected — add for distributed tracing",
                fix_hint="Add 'ops-tracing' to requirements.txt or pyproject.toml",
            )
        ]
