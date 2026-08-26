"""Tests for the shared Python-source analysis layer."""

import ast
import pathlib
import textwrap

import pytest

from charmlint import _ast
from charmlint import _models as models
from charmlint._linter import build_context, lint
from tests.conftest import write_charm_source, write_charmcraft_yaml


def parse(source: str, path: str = "src/charm.py") -> models.Module:
    """Parse a source snippet as if it lived at *path* in a charm."""
    charm_dir = pathlib.PurePosixPath("/charm")
    return _ast.parse(
        pathlib.Path(charm_dir / path), textwrap.dedent(source), pathlib.Path(charm_dir)
    )


def expression(source: str) -> ast.expr:
    """Parse a single expression."""
    return ast.parse(source, mode="eval").body


class TestScope:
    """Files are classified by which part of the charm tree they live in."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("src/charm.py", models.Scope.SRC),
            ("src/nested/helper.py", models.Scope.SRC),
            # A charm's own src/lib/ is charm source, not a vendored library.
            ("src/lib/util.py", models.Scope.SRC),
            ("lib/charms/owner/v0/thing.py", models.Scope.LIB),
            ("tests/unit/test_charm.py", models.Scope.TESTS_UNIT),
            ("tests/integration/test_charm.py", models.Scope.TESTS_INTEGRATION),
            # Test code that is neither of the two named suites.
            ("tests/conftest.py", models.Scope.TESTS),
            ("tests/scenario/test_charm.py", models.Scope.TESTS),
            ("tests/spread/nested/task.py", models.Scope.TESTS),
            ("build.py", models.Scope.OTHER),
        ],
    )
    def test_scope_of_path(self, path: str, expected: models.Scope):
        assert parse("x = 1", path).scope == expected

    def test_path_is_charm_relative_posix(self):
        assert parse("x = 1", "src/nested/helper.py").path == "src/nested/helper.py"


class TestModule:
    """Module.walk filters by node type."""

    def test_walk_filters_by_type(self):
        module = parse("f()\ng()\nx = 1")
        assert len(list(module.walk(ast.Call))) == 2

    def test_walk_without_types_yields_everything(self):
        module = parse("x = 1")
        assert len(list(module.walk())) > 1

    def test_functions_includes_async_and_nested(self):
        module = parse("""
            def outer():
                def inner(): pass
            async def top(): pass
        """)
        assert {f.name for f in module.functions()} == {"outer", "inner", "top"}


class TestDottedName:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("ops", "ops"),
            ("self.model.unit", "self.model.unit"),
            ("ops.main.main", "ops.main.main"),
            # A call or subscript in the chain makes it unreadable statically.
            ("f().attr", None),
            ("d['k'].attr", None),
            ("'literal'.upper", None),
        ],
    )
    def test_dotted_name(self, source: str, expected: str | None):
        assert _ast.dotted_name(expression(source)) == expected


class TestImports:
    def test_plain_import_binds_root(self):
        imports = _ast.Imports.of(parse("import ops"))
        assert imports.resolve(expression("ops.main")) == "ops.main"

    def test_submodule_import_binds_root_not_submodule(self):
        # ``import ops.main`` binds the name ``ops``.
        imports = _ast.Imports.of(parse("import ops.main"))
        assert imports.aliases == {"ops": "ops"}
        assert imports.imports_module("ops")

    def test_aliased_submodule_import(self):
        imports = _ast.Imports.of(parse("import ops.main as m"))
        assert imports.resolve(expression("m.main")) == "ops.main.main"

    def test_from_import(self):
        imports = _ast.Imports.of(parse("from ops import CharmBase"))
        assert imports.resolve(expression("CharmBase")) == "ops.CharmBase"

    def test_from_import_with_alias(self):
        imports = _ast.Imports.of(parse("from time import sleep as nap"))
        assert imports.resolve(expression("nap")) == "time.sleep"

    def test_star_import_binds_nothing(self):
        imports = _ast.Imports.of(parse("from ops import *"))
        assert imports.aliases == {}
        assert imports.imports_module("ops")

    def test_relative_import_ignored(self):
        imports = _ast.Imports.of(parse("from . import helper"))
        assert imports.aliases == {}
        assert not imports.imports_module("helper")

    def test_unimported_name_returned_unchanged(self):
        imports = _ast.Imports.of(parse("x = 1"))
        assert imports.resolve(expression("whatever.thing")) == "whatever.thing"

    def test_imports_module_matches_submodules(self):
        imports = _ast.Imports.of(parse("import ops.tracing"))
        assert imports.imports_module("ops")
        assert not imports.imports_module("op")


class TestCalls:
    def test_call_target_without_imports(self):
        call = expression("ops.main(c)")
        assert isinstance(call, ast.Call)
        assert _ast.call_target(call) == "ops.main"

    def test_call_target_resolves_bare_name_through_imports(self):
        module = parse("from ops import main\nmain(c)")
        imports = _ast.Imports.of(module)
        call = next(module.walk(ast.Call))
        assert _ast.call_target(call, imports) == "ops.main"

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("container.exec(cmd)", "container"),
            ("self.workload_container.exec(cmd)", "workload_container"),
            ("containers[0].exec(cmd)", None),
            ("bare(cmd)", None),
        ],
    )
    def test_receiver(self, source: str, expected: str | None):
        call = expression(source)
        assert isinstance(call, ast.Call)
        assert _ast.receiver(call) == expected

    def test_keyword(self):
        call = expression("c.add_layer('x', layer, combine=True)")
        assert isinstance(call, ast.Call)
        value = _ast.keyword(call, "combine")
        assert isinstance(value, ast.Constant) and value.value is True
        assert _ast.keyword(call, "missing") is None

    def test_keyword_ignores_unpacking(self):
        call = expression("f(**kwargs)")
        assert isinstance(call, ast.Call)
        assert _ast.keyword(call, "combine") is None


class TestObservers:
    @pytest.mark.parametrize(
        ("source", "event", "action"),
        [
            (
                "self.framework.observe(self.on.do_thing_action, self._h)",
                "do_thing_action",
                "do-thing",
            ),
            ("framework.observe(self.on.do_thing_action, self._h)", "do_thing_action", "do-thing"),
            (
                "self.framework.observe(self.on['do-thing'].action, self._h)",
                "do_thing_action",
                "do-thing",
            ),
            (
                "self.framework.observe(getattr(self.on, 'do_thing_action'), self._h)",
                "do_thing_action",
                "do-thing",
            ),
            ("self.framework.observe(self.on.config_changed, self._h)", "config_changed", None),
            (
                "self.framework.observe(self.on['db'].relation_changed, self._h)",
                "db_relation_changed",
                None,
            ),
        ],
    )
    def test_event_spellings(self, source: str, event: str, action: str | None):
        (observer,) = _ast.observers(parse(source))
        assert observer.event == event
        assert observer.action == action
        assert observer.resolved

    def test_handler_name(self):
        (observer,) = _ast.observers(
            parse("self.framework.observe(self.on.start, self._on_start)")
        )
        assert observer.handler == "_on_start"

    def test_handler_on_another_object_is_unresolved(self):
        (observer,) = _ast.observers(parse("self.framework.observe(self.on.start, other.handle)"))
        assert observer.handler is None

    def test_named_constant_subscript_is_unresolved(self):
        # ``self.on[FOO].action`` is an ast.Name; guessing its value would be
        # worse than reporting the observer unresolved.
        (observer,) = _ast.observers(parse("self.framework.observe(self.on[FOO].action, self._h)"))
        assert observer.event is None
        assert not observer.resolved

    @pytest.mark.parametrize(
        "event_expr",
        [
            # Not a getattr call.
            "helper(self.on)",
            # getattr with too few arguments to name an event.
            "getattr(self.on)",
            # getattr on something that isn't an event source.
            "getattr(self.thing, 'start')",
            # getattr with a computed name.
            "getattr(self.on, NAME)",
            # Not an attribute access at all.
            "EVENTS[0]",
            # An attribute chain that never passes through ``.on``.
            "self.thing.start",
            # A subscript on something that isn't an event source.
            "self.events['db'].relation_changed",
        ],
    )
    def test_unreadable_event_expressions_are_unresolved(self, event_expr: str):
        (observer,) = _ast.observers(parse(f"self.framework.observe({event_expr}, self._h)"))
        assert observer.event is None
        assert not observer.resolved

    def test_resolve_of_nothing_is_none(self):
        assert _ast.Imports.of(parse("x = 1")).resolve(None) is None

    def test_unrelated_observe_like_call_ignored(self):
        assert _ast.observers(parse("thing.observe(one_arg)")) == []

    def test_non_observe_call_ignored(self):
        assert _ast.observers(parse("self.framework.reemit(self.on.start, self._h)")) == []


class TestWalkStatements:
    def continuations(self, source: str) -> dict[str, str | None]:
        """Map each expression-statement's source text to what runs next."""
        tree = ast.parse(textwrap.dedent(source))
        out: dict[str, str | None] = {}
        for statement, following in _ast.walk_statements(tree.body):
            if isinstance(statement, ast.Expr):
                key = ast.unparse(statement)
                out[key] = None if following is None else type(following).__name__
        return out

    def test_next_sibling_is_the_continuation(self):
        assert self.continuations("a()\nreturn_value = 1") == {"a()": "Assign"}

    def test_last_statement_of_if_resumes_after_the_if(self):
        result = self.continuations("""
            if c:
                a()
            b()
        """)
        assert result["a()"] == "Expr"

    def test_last_statement_of_else_resumes_after_the_if(self):
        result = self.continuations("""
            if c:
                pass
            else:
                a()
            b()
        """)
        assert result["a()"] == "Expr"

    def test_nothing_follows_the_final_statement(self):
        assert self.continuations("if c:\n    a()") == {"a()": None}

    def test_except_handler_body_is_walked(self):
        result = self.continuations("""
            try:
                pass
            except ValueError:
                a()
            b()
        """)
        assert result["a()"] == "Expr"

    def test_nested_function_body_has_no_continuation(self):
        # ``a()`` does not run where the def sits, so nothing here follows it.
        result = self.continuations("""
            def f():
                a()
            b()
        """)
        assert result["a()"] is None

    def test_lambda_body_is_not_a_statement_list(self):
        assert self.continuations("f = lambda: a()") == {}


class TestIsTerminal:
    @pytest.mark.parametrize("source", ["return", "raise ValueError()", "continue", "break"])
    def test_terminal_statements(self, source: str):
        statement = ast.parse(f"while True:\n    {source}").body[0]
        assert isinstance(statement, ast.While)
        assert _ast.is_terminal(statement.body[0])

    def test_nothing_following_counts_as_terminal(self):
        assert _ast.is_terminal(None)

    def test_plain_call_is_not_terminal(self):
        assert not _ast.is_terminal(ast.parse("a()").body[0])


class TestDictLiterals:
    def dict_node(self, source: str) -> ast.Dict:
        node = expression(source)
        assert isinstance(node, ast.Dict)
        return node

    def test_dict_keys(self):
        assert self.dict_keys_of("{'a': 1, 'b': 2}") == {"a", "b"}

    def dict_keys_of(self, source: str) -> set[str]:
        return _ast.dict_keys(self.dict_node(source))

    def test_computed_and_unpacked_keys_skipped(self):
        assert self.dict_keys_of("{**base, key: 1, 'c': 2, 3: 'x'}") == {"c"}

    def test_dict_get(self):
        value = _ast.dict_get(self.dict_node("{'a': 1, 'b': 2}"), "b")
        assert isinstance(value, ast.Constant) and value.value == 2

    def test_dict_get_missing(self):
        assert _ast.dict_get(self.dict_node("{'a': 1}"), "b") is None

    def test_dict_get_skips_unpacking(self):
        assert _ast.dict_get(self.dict_node("{**base}"), "a") is None


class TestParsingInTheCore:
    """Parsing happens once, in the linter core — see #191."""

    def test_context_carries_parsed_modules(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n")
        context = build_context(tmp_charm)
        assert [m.path for m in context.charm_sources()] == ["src/charm.py"]

    def test_lib_is_collected_but_not_a_charm_source(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n")
        lib = tmp_charm / "lib" / "charms" / "owner" / "v0"
        lib.mkdir(parents=True)
        (lib / "thing.py").write_text("import ops\n")
        context = build_context(tmp_charm)
        assert [m.path for m in context.charm_sources()] == ["src/charm.py"]
        assert [m.path for m in context.modules(models.Scope.LIB)] == [
            "lib/charms/owner/v0/thing.py"
        ]

    def test_tests_are_collected_with_their_own_scopes(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        for kind in ("unit", "integration"):
            directory = tmp_charm / "tests" / kind
            directory.mkdir(parents=True)
            (directory / "test_charm.py").write_text("def test_x(): pass\n")
        context = build_context(tmp_charm)
        assert [m.path for m in context.modules(models.Scope.TESTS_UNIT)] == [
            "tests/unit/test_charm.py"
        ]
        assert [m.path for m in context.modules(models.Scope.TESTS_INTEGRATION)] == [
            "tests/integration/test_charm.py"
        ]

    def test_unrecognised_test_suite_falls_back_to_tests(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        directory = tmp_charm / "tests" / "scenario"
        directory.mkdir(parents=True)
        (directory / "test_charm.py").write_text("def test_x(): pass\n")
        (tmp_charm / "tests" / "conftest.py").write_text("import pytest\n")
        context = build_context(tmp_charm)
        assert [m.path for m in context.modules(models.Scope.TESTS)] == [
            "tests/conftest.py",
            "tests/scenario/test_charm.py",
        ]
        assert list(context.modules(models.Scope.OTHER)) == []

    def test_modules_without_scopes_yields_everything(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "import ops\n")
        context = build_context(tmp_charm)
        assert list(context.modules()) == context.python_modules

    def test_syntax_error_is_fatal_not_silently_skipped(self, tmp_charm: pathlib.Path):
        write_charmcraft_yaml(tmp_charm, {"name": "test"})
        write_charm_source(tmp_charm, "def broken(\n")
        report = lint(tmp_charm)
        diagnostics = list(report)
        assert [d.rule_id for d in diagnostics] == ["FATAL"]
        assert "charm.py" in diagnostics[0].message
        assert "could not parse" in diagnostics[0].message
