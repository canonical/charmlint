"""Python source analysis for rules — parsed modules and shared matchers.

The Python-side counterpart to ``_yaml.py``. Where that module gives rules
YAML values that carry their own file and line, this one gives them parsed
modules that carry their own path and scope, plus the matchers that more
than one rule has already needed.

Rules should reach for ``context.charm_sources()`` rather than iterating
``context.python_sources`` and parsing it themselves: parsing happens once
in the linter core, so a rule never sees an unparseable file and never has
to decide what to do about one. :class:`models.Module` and
:class:`models.Scope` live in ``_models`` alongside the other data models.

Sections, in call order: parsing, then name resolution, then the matcher
families built on it — imports, calls, observers, statements, literals.

A matcher belongs here once a second rule wants it; until then it stays
with the rule that needs it.
"""

import ast
import dataclasses
import pathlib
import warnings
from collections.abc import Iterator, Sequence

from . import _models as models


def _library_owner(name: str) -> str:
    """Return the ``lib/charms/`` directory name a charm publishes under.

    Charmhub names are hyphenated and Python packages are not, so
    ``my-charm`` publishes into ``lib/charms/my_charm/``.
    """
    return name.replace("-", "_")


def _scope_of(relative: pathlib.PurePosixPath, charm_name: str | None) -> models.Scope:
    """Classify a charm-relative path into a :class:`models.Scope`."""
    parts = relative.parts
    # Longest prefix first, so the two named suites beat the generic fallback.
    if parts[:2] == ("tests", "unit"):
        return models.Scope.TESTS_UNIT
    if parts[:2] == ("tests", "integration"):
        return models.Scope.TESTS_INTEGRATION
    if parts[:1] == ("tests",):
        return models.Scope.TESTS_OTHER
    # Only the top-level lib/ is library code — a charm's own ``src/lib/``
    # is charm source.
    if parts[:1] == ("lib",):
        # Everything under lib/charms/ is laid out as ``<owner>/vN/<lib>.py``.
        # The charm publishing the library owns that directory; every other
        # owner is a vendored copy of someone else's work.
        owner = parts[2] if parts[:2] == ("lib", "charms") and len(parts) > 2 else None
        if owner is not None and charm_name and owner == _library_owner(charm_name):
            return models.Scope.OWNED_LIB
        return models.Scope.VENDORED_LIB
    if parts[:1] == ("src",):
        return models.Scope.SRC
    return models.Scope.OTHER


def parse(
    file: pathlib.Path,
    text: str,
    charm_dir: pathlib.Path,
    charm_name: str | None = None,
) -> models.Module:
    """Parse one source file into a :class:`Module`.

    *charm_name* is the charm's declared name, which tells a library this
    charm publishes apart from a vendored copy of someone else's. Without
    it, everything under ``lib/`` is taken to be vendored.

    Raises :class:`SyntaxError` — with ``filename`` set — for an unparseable
    source. The linter core turns that into a fatal diagnostic; rules never
    see it.
    """
    relative = pathlib.PurePosixPath(file.relative_to(charm_dir).as_posix())
    with warnings.catch_warnings():
        # Compiling the charm's code can warn about it (an invalid escape
        # sequence, say). That is for ruff to report, not for charmlint to
        # print to stderr in the middle of its own output.
        warnings.simplefilter("ignore")
        tree = ast.parse(text, filename=str(file))
    return models.Module(
        path=str(relative),
        file=file,
        text=text,
        tree=tree,
        scope=_scope_of(relative, charm_name),
    )


# --- Name resolution -------------------------------------------------------


def dotted_name(node: ast.AST) -> str | None:
    """Return the dotted source spelling of an attribute chain, else ``None``.

    ``self.model.unit`` → ``"self.model.unit"``; ``ops`` → ``"ops"``. Only
    plain ``Name``/``Attribute`` chains resolve — a subscript or a call
    anywhere in the chain makes the whole thing unreadable statically, and
    ``None`` is the honest answer.
    """
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


# --- Imports ---------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Imports:
    """The names a module's imports bind, and what they resolve to.

    Lets a rule ask "does this name mean ``time.sleep`` here?" without
    assuming a spelling, so that ``from time import sleep`` is as visible
    as ``time.sleep``.

    Relative imports (``from . import x``) are ignored: resolving them needs
    the charm's package layout.
    """

    aliases: dict[str, str]
    modules: frozenset[str]

    @classmethod
    def of(cls, module: models.Module) -> "Imports":
        """Build the import table for *module*."""
        aliases: dict[str, str] = {}
        imported: set[str] = set()
        for node in module.walk(ast.Import, ast.ImportFrom):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imported.add(name.name)
                    # ``import a.b`` binds ``a``, not ``a.b``; ``import a.b as c``
                    # binds ``c`` to the submodule.
                    if name.asname:
                        aliases[name.asname] = name.name
                    else:
                        root = name.name.split(".", 1)[0]
                        aliases[root] = root
            elif node.level == 0 and node.module:
                imported.add(node.module)
                for name in node.names:
                    if name.name != "*":
                        aliases[name.asname or name.name] = f"{node.module}.{name.name}"
        return cls(aliases=aliases, modules=frozenset(imported))

    def resolve(self, node: ast.AST | str | None) -> str | None:
        """Resolve an expression (or dotted spelling) to its canonical name.

        With ``from ops import main as m``, ``m.main`` resolves to
        ``ops.main.main``. An unimported root is returned unchanged, so a
        caller comparing against a canonical name simply won't match.
        """
        dotted = node if isinstance(node, str) else (dotted_name(node) if node else None)
        if dotted is None:
            return None
        root, _, rest = dotted.partition(".")
        target = self.aliases.get(root)
        if target is None:
            return dotted
        return f"{target}.{rest}" if rest else target

    def imports_module(self, name: str) -> bool:
        """Whether *name* — or a submodule of it — is imported anywhere."""
        return any(mod == name or mod.startswith(f"{name}.") for mod in self.modules)


# The canonical names :meth:`Imports.resolve` gives ops' charm base class and
# its entry point. ``ops.main`` is both the submodule and the callable inside it.
CHARM_BASES = frozenset({"ops.CharmBase", "ops.charm.CharmBase"})
OPS_MAIN_TARGETS = frozenset({"ops.main", "ops.main.main"})


# --- Calls -----------------------------------------------------------------


def call_target(call: ast.Call, imports: Imports | None = None) -> str | None:
    """Return the dotted name being called, resolved through *imports*.

    ``ops.main(c)`` → ``"ops.main"``. With an :class:`Imports` table and
    ``from ops import main``, a bare ``main(c)`` resolves to ``"ops.main"``
    too. Returns ``None`` when the callee isn't a plain name chain.
    """
    if imports is not None:
        return imports.resolve(call.func)
    return dotted_name(call.func)


def receiver(call: ast.Call) -> str | None:
    """Return the trailing name of a method call's receiver, else ``None``.

    For ``self.workload_container.exec(...)`` this is ``"workload_container"``
    and for ``container.exec(...)`` it is ``"container"``. Rules use it as a
    naming heuristic where no type information is available — charmlint has
    no type inference, so ``exec`` on an unrelated object is indistinguishable
    from ``Container.exec`` except by what the variable is called.
    """
    if not isinstance(call.func, ast.Attribute):
        return None
    value = call.func.value
    if isinstance(value, ast.Attribute):
        return value.attr
    if isinstance(value, ast.Name):
        return value.id
    return None


def keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value of keyword argument *name*, or ``None``.

    ``**kwargs`` unpacking has no keyword name and is skipped, so an
    unresolvable call reads as "argument absent".
    """
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


# --- Observers -------------------------------------------------------------

# ``framework.observe`` is reached as ``self.framework.observe`` and as a bare
# ``framework.observe`` (the kwarg-injected form), so observe calls are matched
# on the method name alone rather than on the receiver.
_OBSERVE = "observe"
_ACTION_SUFFIX = "_action"


@dataclasses.dataclass(frozen=True)
class Observer:
    """One ``framework.observe(...)`` call, decoded.

    ``event`` is the underscore-spelled ops event name (``config_changed``,
    ``do_thing_action``) regardless of which spelling the source used.
    ``handler`` is the method name when the second argument is ``self.<name>``.

    ``resolved`` is ``False`` when the call is an observe call whose event
    expression could not be read statically — a name-constant subscript, say.
    A rule that reasons about which events reach a handler must treat an
    unresolved observer conservatively rather than ignoring it, or it will
    report on charms it simply failed to understand.
    """

    event: str | None
    handler: str | None
    call: ast.Call
    resolved: bool

    @property
    def action(self) -> str | None:
        """The hyphenated action name, when this observes an action event."""
        if self.event is None or not self.event.endswith(_ACTION_SUFFIX):
            return None
        return self.event[: -len(_ACTION_SUFFIX)].replace("_", "-")


def observers(module: models.Module) -> list[Observer]:
    """Decode every ``framework.observe(...)`` call in *module*."""
    found: list[Observer] = []
    for call in module.walk(ast.Call):
        if not isinstance(call.func, ast.Attribute) or call.func.attr != _OBSERVE:
            continue
        if len(call.args) < 2:
            continue
        event = _event_name(call.args[0])
        found.append(
            Observer(
                event=event,
                handler=_handler_name(call.args[1]),
                call=call,
                resolved=event is not None,
            )
        )
    return found


def _event_name(expr: ast.expr) -> str | None:
    """Return the underscored event name for an observe call's first argument.

    Recognises the three spellings ops accepts:

    * ``self.on.<event>`` — plain attribute access.
    * ``self.on['<name>'].<event>`` — the subscript returns a
      ``PrefixedEvents`` wrapper whose attribute is the same ``BoundEvent``
      as the attribute form.
    * ``getattr(self.on, '<event>')`` — dynamic lookup, common in charms
      that build the event reference from a constant.

    Only literal string keys resolve in the subscript form:
    ``self.on[FOO].action`` is an ``ast.Name``, and guessing at its value
    would be worse than reporting it unresolved.
    """
    # getattr(<...>.on, '<event>')
    if isinstance(expr, ast.Call):
        if not (isinstance(expr.func, ast.Name) and expr.func.id == "getattr"):
            return None
        if len(expr.args) < 2:
            return None
        target, key = expr.args[0], expr.args[1]
        if not (isinstance(target, ast.Attribute) and target.attr == "on"):
            return None
        return dict_key(key)
    if not isinstance(expr, ast.Attribute):
        return None
    parent = expr.value
    # <...>.on.<event>
    if isinstance(parent, ast.Attribute) and parent.attr == "on":
        return expr.attr
    # <...>.on['<name>'].<event>
    if not isinstance(parent, ast.Subscript):
        return None
    grandparent = parent.value
    if not (isinstance(grandparent, ast.Attribute) and grandparent.attr == "on"):
        return None
    prefix = dict_key(parent.slice)
    if prefix is None:
        return None
    # The prefix is the endpoint/action name as Juju spells it, hyphenated;
    # the event name it forms is underscored, like every other ops event.
    return f"{prefix.replace('-', '_')}_{expr.attr}"


def _handler_name(expr: ast.expr) -> str | None:
    """Return the method name for an observe call's handler argument.

    Only ``self.<method>`` resolves. A handler on another object is a method
    this module cannot see, and reporting a name for it would invite a rule
    to match the wrong function.
    """
    if (
        isinstance(expr, ast.Attribute)
        and isinstance(expr.value, ast.Name)
        and expr.value.id == "self"
    ):
        return expr.attr
    return None


# --- Statements ------------------------------------------------------------

# Bodies that hold a statement list. ``orelse`` covers else on if/for/while
# and ``finalbody`` the finally clause; except handlers are reached
# separately, since they hang off ``handlers`` rather than an attribute of
# statements.
_BODY_FIELDS = ("body", "orelse", "finalbody")


def walk_statements(
    body: Sequence[ast.stmt], after: ast.stmt | None = None
) -> Iterator[tuple[ast.stmt, ast.stmt | None]]:
    """Yield each statement in *body*, recursively, with what runs next.

    The continuation is the statement that executes after this one when it
    completes normally, or ``None`` when nothing does — the answer to "is
    this ``event.defer()`` followed by a ``return``?", which ``ast.walk``
    cannot give because it discards ordering.

    *after* is the continuation for the last statement of *body*: at the end
    of an ``if`` branch, control resumes after the whole ``if``.

    Two deliberate approximations, both favouring false negatives over false
    positives: a loop body's last statement is reported as having nothing
    after it rather than looping back, and a ``finally`` block is walked as
    if it were reached normally. A nested function or class body gets a
    ``None`` continuation, because its statements do not run here at all.
    """
    for index, statement in enumerate(body):
        # The last statement of this body is followed by whatever follows the
        # block that contains it.
        following = body[index + 1] if index + 1 < len(body) else after
        yield statement, following
        nested = (
            None
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            else following
        )
        for field in _BODY_FIELDS:
            inner = getattr(statement, field, None)
            # On a lambda or a conditional expression, ``body`` is a single
            # expression node rather than a statement list.
            if isinstance(inner, list):
                yield from walk_statements(inner, nested)
        for handler in getattr(statement, "handlers", []):
            yield from walk_statements(handler.body, nested)


def is_terminal(statement: ast.stmt | None) -> bool:
    """Whether *statement* ends the current flow rather than falling through.

    ``None`` — nothing follows — counts as terminal: a call that must be the
    last thing a function does is satisfied by being the last thing it does.
    """
    return statement is None or isinstance(
        statement, ast.Return | ast.Raise | ast.Continue | ast.Break
    )


# --- Literals --------------------------------------------------------------


def dict_key(key: ast.expr | None) -> str | None:
    """Return a dict literal key's string value, else ``None``.

    ``key`` is ``None`` for a ``**unpacking`` entry, which has no key at all;
    a computed key is an expression that cannot be resolved statically.
    """
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    return None


def dict_keys(node: ast.Dict) -> set[str]:
    """Return the string-literal keys of a dict literal."""
    return {key for key in (dict_key(k) for k in node.keys) if key is not None}


def dict_get(node: ast.Dict, name: str) -> ast.expr | None:
    """Return the value node for string-literal key *name*, else ``None``."""
    for key, value in zip(node.keys, node.values, strict=True):
        if dict_key(key) == name:
            return value
    return None
