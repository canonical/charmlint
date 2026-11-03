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
        assert found[0].severity == Severity.INFO
        assert found[0].line == 8
        assert "1 logging call" in found[0].message

    def test_while_loop_and_self_logger_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            class C:
                def f(self):
                    while self.more():
                        self._logger.info("tick")
            """,
        )
        assert len(found) == 1

    def test_reported_once_per_outermost_loop(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(items):
                for a in items:
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
            def f(items):
                for item in items:
                    process(item)
                logger.info("done")
            """,
        )
        assert found == []

    def test_for_else_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(items):
                for item in items:
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
            def f(items):
                for item in items:
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
            def f(items):
                for item in items:
                    def callback(xs):
                        for x in xs:
                            logger.info("x")
            """,
        )
        assert len(found) == 1
        assert found[0].line == 5

    def test_non_logger_receiver_not_flagged(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(items):
                for item in items:
                    item.debug("x")
                    print(item)
            """,
        )
        assert found == []

    def test_noqa_suppresses(self, tmp_charm: pathlib.Path):
        found = _lint_source(
            tmp_charm,
            """\
            def f(items):
                for item in items:
                    logger.warning("bad")  # charmlint: ignore[PERFORMANCE-001]
            """,
        )
        assert found == []
