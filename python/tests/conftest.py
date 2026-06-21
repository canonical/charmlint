"""Shared fixtures for charmlint tests."""

import pathlib
from typing import Any

import pytest
import yaml


@pytest.fixture
def tmp_charm(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a minimal charm directory and return its path."""
    charm_dir = tmp_path / "test-charm"
    charm_dir.mkdir()
    (charm_dir / "src").mkdir()
    return charm_dir


def write_charmcraft_yaml(charm_dir: pathlib.Path, data: dict[str, Any]) -> None:
    """Write a charmcraft.yaml file to a charm directory."""
    with (charm_dir / "charmcraft.yaml").open("w") as f:
        yaml.dump(data, f)


def write_charm_source(charm_dir: pathlib.Path, content: str, filename: str = "charm.py") -> None:
    """Write a Python source file to the charm's src/ directory."""
    (charm_dir / "src" / filename).write_text(content)


def make_full_charm(charm_dir: pathlib.Path) -> None:
    """Populate a charm directory with metadata that passes most checks."""
    write_charmcraft_yaml(
        charm_dir,
        {
            "name": "test-charm",
            "display-name": "Test Charm",
            "summary": "A test charm for charmlint",
            "description": "A test charm used in charmlint unit tests.",
            "docs": "https://example.com/docs",
            "issues": "https://example.com/issues",
            "source": "https://example.com/source",
            "requires": {
                "tracing": {"interface": "tracing"},
                "logging": {"interface": "loki_push_api"},
                "grafana-dashboard": {"interface": "grafana_dashboard"},
            },
            "provides": {
                "metrics-endpoint": {"interface": "prometheus_scrape"},
            },
            "config": {
                "options": {
                    "port": {
                        "type": "int",
                        "default": 8080,
                        "description": "HTTP port",
                    },
                },
            },
            "actions": {
                "get-health": {"description": "Check workload health"},
                "pause": {"description": "Pause the workload"},
                "resume": {"description": "Resume the workload"},
            },
        },
    )
    write_charm_source(
        charm_dir,
        """\
import ops
from ops import BlockedStatus, WaitingStatus

class TestCharm(ops.CharmBase):
    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.framework.observe(self.on.get_health_action, self._on_get_health)
        self.framework.observe(self.on.pause_action, self._on_pause)
        self.framework.observe(self.on.resume_action, self._on_resume)

    def _reconcile(self) -> None:
        if not self.config.get("port"):
            self.unit.status = BlockedStatus("missing config: port")
        if self.config.get("invalid-combo"):
            self.unit.status = BlockedStatus("invalid config")
        if not self.model.relations.get("database"):
            self.unit.status = BlockedStatus("missing relation: database")

    def _on_get_health(self, event: ops.ActionEvent) -> None:
        event.set_results({"status": "ok"})

    def _on_pause(self, event: ops.ActionEvent) -> None:
        event.set_results({"status": "paused"})

    def _on_resume(self, event: ops.ActionEvent) -> None:
        event.set_results({"status": "running"})
""",
    )
    # Add requirements with ops-tracing.
    (charm_dir / "requirements.txt").write_text("ops\nops-tracing\n")
    # Add README.
    (charm_dir / "README.md").write_text(
        "# Test Charm\n\n## Installation\n\n## Configuration\n\n## Usage\n\n## Troubleshooting\n"
    )
    (charm_dir / "LICENSE").write_text("Apache-2.0")
    (charm_dir / "icon.svg").write_text("<svg/>")
    # Add test directories.
    (charm_dir / "tests" / "unit").mkdir(parents=True)
    (charm_dir / "tests" / "unit" / "test_charm.py").write_text("def test_placeholder(): pass\n")
    (charm_dir / "tests" / "integration").mkdir(parents=True)
    (charm_dir / "tests" / "integration" / "test_charm.py").write_text(
        "def test_placeholder(): pass\n"
    )
