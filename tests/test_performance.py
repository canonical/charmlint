"""Tests for PERFORMANCE-### rules."""

import pathlib
import textwrap

from charmlint._linter import lint
from charmlint._models import Severity
from tests.conftest import write_charm_source, write_charmcraft_yaml

RULE = "PERFORMANCE-001"


def _lint_source(charm_dir: pathlib.Path, source: str):
    write_charmcraft_yaml(charm_dir, {"name": "test"})
    write_charm_source(charm_dir, textwrap.dedent(source))
    return [d for d in lint(charm_dir) if d.rule_id == RULE]


class TestLoggingInLoop:
    """PERFORMANCE-001 — logging calls inside a loop."""

    def test_for_loop_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            import logging

            logger = logging.getLogger(__name__)


            def f(relations):
                for relation in relations:
                    logger.debug("relation %s", relation)
            """,
        )
        assert len(found) == 1
        assert found[0].severity == Severity.WARNING
        assert found[0].line == 8
        assert "1 logging call" in found[0].message

    def test_self_logger_over_model_relations_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            class C:
                def f(self):
                    for relation in self.model.relations["metrics"]:
                        self._logger.info("tick")
            """,
        )
        assert len(found) == 1

    def test_units_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relation):
                for unit in relation.units:
                    logger.debug("unit %s", unit)
            """,
        )
        assert len(found) == 1

    def test_while_loop_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(self):
                while self.more_relations():
                    logger.info("tick")
            """,
        )
        assert found == []

    def test_other_collections_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(rules, retries):
                for name, rule in rules.items():
                    logger.debug("rule %s", name)
                for attempt in range(retries):
                    logger.warning("attempt %d", attempt)
            """,
        )
        assert found == []

    def test_literal_list_named_after_relation_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(self):
                for step in [self._ensure_secrets, self._ensure_cluster_relation]:
                    logger.debug("running %s", step)
                    step()
            """,
        )
        assert found == []

    def test_relation_loop_inside_other_loop(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(self, endpoints):
                for endpoint in endpoints:
                    logger.info("endpoint")
                    for relation in self.model.relations[endpoint]:
                        logger.info("relation")
            """,
        )
        assert len(found) == 1
        assert found[0].line == 5

    def test_reported_once_per_outermost_loop(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relations):
                for a in relations:
                    logger.info("a")
                    for b in a:
                        logger.info("b")
                        logger.debug("c")
            """,
        )
        assert len(found) == 1
        assert found[0].line == 3
        assert "3 logging calls" in found[0].message

    def test_logging_after_loop_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relations):
                for item in relations:
                    process(item)
                logger.info("done")
            """,
        )
        assert found == []

    def test_for_else_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relations):
                for item in relations:
                    process(item)
                else:
                    logger.info("no break")
            """,
        )
        assert found == []

    def test_nested_function_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relations):
                for item in relations:
                    def callback():
                        logger.info("later")
                    register(callback)
            """,
        )
        assert found == []

    def test_loop_inside_function_in_loop_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relations):
                for item in relations:
                    def callback(relation):
                        for x in relation.units:
                            logger.info("x")
            """,
        )
        assert len(found) == 1
        assert found[0].line == 5

    def test_non_logger_receiver_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relations):
                for item in relations:
                    item.debug("x")
                    print(item)
            """,
        )
        assert found == []

    def test_noqa_suppresses(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(relations):
                for item in relations:
                    logger.warning("bad")  # charmlint: ignore[PERFORMANCE-001]
            """,
        )
        assert found == []
