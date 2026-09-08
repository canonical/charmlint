"""Relation rules — what a charm writes into a relation databag.

Juju compares databag contents byte for byte, so a value whose textual
form changes between reconciliations without the underlying facts having
changed is republished as a change: the peer is woken with
``relation-changed``, republishes its own unstable data, and the two
charms flap. See `Your charm might be flapping its databags
<https://discourse.charmhub.io/t/your-charm-might-be-flapping-its-databags/20715>`_.

The rules here catch the instability that is visible within a single
expression — an unordered collection, a freshly generated value, a
dictionary serialised without sorting its keys. A value that becomes
unstable somewhere else and is carried to the databag through a local or
a helper needs data flow to follow, and is out of scope.
"""

import ast
from collections.abc import Callable, Iterator

from .. import _ast
from .. import _models as models
from ._base import Rule

_FLAPPING_URL = "https://discourse.charmhub.io/t/your-charm-might-be-flapping-its-databags/20715"


class UnorderedValueInDatabag(Rule):
    """Flag an unordered collection written into a relation databag."""

    category = "RELATIONS"
    number = 3
    name = "unordered-value-in-databag"
    description = "Unordered collection written to a relation databag"
    default_severity = models.Severity.WARNING
    reference_url = _FLAPPING_URL

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"{reason} is written to a relation databag — it can "
                "serialise in a different order each reconciliation, so "
                "Juju sees a change and wakes the peer charm for nothing",
                path=path,
                line=line,
                fix_hint=(
                    "Sort the value before writing it — `sorted(...)` "
                    "around the collection gives the same bytes every "
                    "time the contents are the same"
                ),
            )
            for path, line, reason in _findings(context, _unordered_source, _ORDER_SANITISERS)
        ]


class NondeterministicValueInDatabag(Rule):
    """Flag a freshly generated value written into a relation databag."""

    category = "RELATIONS"
    number = 4
    name = "nondeterministic-value-in-databag"
    description = "Freshly generated value written to a relation databag"
    default_severity = models.Severity.WARNING
    reference_url = _FLAPPING_URL

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"{reason} is written to a relation databag — it differs "
                "on every reconciliation, so Juju sees a change and wakes "
                "the peer charm even when nothing has actually changed",
                path=path,
                line=line,
                fix_hint=(
                    "Write a value derived from the facts being shared, "
                    "or generate the value once and keep it (in a peer "
                    "databag or a secret) rather than regenerating it "
                    "each time"
                ),
            )
            for path, line, reason in _findings(context, _nondeterministic_source, frozenset())
        ]


class UnsortedJsonInDatabag(Rule):
    """Flag ``json.dumps()`` into a databag without ``sort_keys=True``."""

    category = "RELATIONS"
    number = 5
    name = "unsorted-json-in-databag"
    description = "json.dumps() into a relation databag without sort_keys=True"
    default_severity = models.Severity.INFO
    reference_url = _FLAPPING_URL

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                "`json.dumps()` writes to a relation databag without "
                "`sort_keys=True` — if the mapping is ever built in a "
                "different order the bytes change, and Juju wakes the "
                "peer charm for nothing",
                path=path,
                line=line,
                fix_hint="Pass `sort_keys=True` to `json.dumps()`",
            )
            for path, line, _ in _findings(context, _unsorted_json_dump, frozenset())
        ]


# Callables whose result is as unstable as their argument, so a rule
# should look through them to what was passed in. ``json.dumps`` is here
# because ``sort_keys=True`` orders a mapping's keys and does nothing for
# the order of a list — RELATIONS-005 is what asks about the keys.
_TRANSPARENT_CALLS = frozenset(
    {"list", "tuple", "dict", "str", "repr", "json.dumps", "yaml.dump", "yaml.safe_dump"}
)

# Methods that reformat their receiver without reordering it, so the
# instability of ``",".join(x)`` or ``x.isoformat()`` is the instability
# of ``x``.
_TRANSPARENT_METHODS = frozenset(
    {"join", "format", "encode", "decode", "hex", "isoformat", "strftime"}
)

# Calls that settle an order, so nothing below them is unordered any more.
_ORDER_SANITISERS = frozenset({"sorted"})

# Calls that build a sequence rather than a mapping.
_SEQUENCE_CALLS = frozenset({"sorted", "list", "tuple", "set", "frozenset"})

# Calls whose result has no defined order. ``set`` and ``frozenset`` cover
# the constructors; the set-algebra and directory-walking methods are
# matched by name because their receiver's type is unknowable statically.
_UNORDERED_CALLS = {
    "set": "A set",
    "frozenset": "A frozen set",
    "glob.glob": "A glob result",
    "glob.iglob": "A glob result",
    "os.listdir": "A directory listing",
    "os.scandir": "A directory listing",
}
_UNORDERED_METHODS = {
    "union": "A set",
    "intersection": "A set",
    "difference": "A set",
    "symmetric_difference": "A set",
    "iterdir": "A directory listing",
    "rglob": "A glob result",
}

# Calls that answer differently every time they are made.
_NONDETERMINISTIC_CALLS = {
    "uuid.uuid1": "A freshly generated UUID",
    "uuid.uuid4": "A freshly generated UUID",
    "time.time": "The current time",
    "time.time_ns": "The current time",
    "time.monotonic": "The current time",
    "datetime.datetime.now": "The current time",
    "datetime.datetime.utcnow": "The current time",
    "datetime.datetime.today": "The current time",
    "os.urandom": "Freshly generated random bytes",
    "secrets.token_bytes": "A freshly generated token",
    "secrets.token_hex": "A freshly generated token",
    "secrets.token_urlsafe": "A freshly generated token",
    "random.random": "A random value",
    "random.randint": "A random value",
    "random.choice": "A random value",
    "random.sample": "A random value",
}


def _findings(
    context: models.CharmContext,
    match: Callable[[ast.expr, _ast.Imports], str | None],
    sanitisers: frozenset[str],
) -> Iterator[tuple[str, int, str]]:
    """Yield ``(path, line, reason)`` for each databag write *match* rejects.

    *match* is applied to every expression whose value reaches a databag
    write, stopping at *sanitisers* — a call that fixes the property
    *match* is looking for makes everything below it uninteresting.
    """
    for module in context.charm_sources():
        imports = _ast.Imports.of(module)
        for written in _databag_values(module):
            for expr in _reachable(written, imports, sanitisers):
                reason = match(expr, imports)
                if reason is not None:
                    yield module.path, expr.lineno, reason
                    break


def _databag_values(module: models.Module) -> Iterator[ast.expr]:
    """Yield every expression written into a relation databag.

    ops models relation data as a mapping of mappings, so a write is
    recognised by that shape: ``<relation>.data[<entity>][<key>] = ...``
    for a single key, and ``<relation>.data[<entity>].update({...})`` for
    several at once. A databag bound to a local first — ``bag =
    relation.data[self.app]`` — needs data flow to follow and is missed.
    """
    for node in module.walk(ast.Assign, ast.AnnAssign, ast.Call):
        if isinstance(node, ast.Call):
            yield from _update_values(node)
            continue
        if node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(_is_databag_entry(target) for target in targets):
            yield node.value


def _update_values(call: ast.Call) -> Iterator[ast.expr]:
    """Yield the values a ``<databag>.update(...)`` call writes."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "update":
        return
    if not _is_databag(func.value):
        return
    for arg in call.args:
        if isinstance(arg, ast.Dict):
            yield from arg.values
    for keyword in call.keywords:
        # ``**other`` has no key of its own and nothing to look inside.
        if keyword.arg is not None:
            yield keyword.value


def _is_databag_entry(node: ast.expr) -> bool:
    """True for ``<relation>.data[<entity>][<key>]`` — one databag entry."""
    return isinstance(node, ast.Subscript) and _is_databag(node.value)


def _is_databag(node: ast.expr) -> bool:
    """True for ``<relation>.data[<entity>]`` — one whole databag."""
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "data"
    )


def _reachable(
    expr: ast.expr, imports: _ast.Imports, sanitisers: frozenset[str]
) -> Iterator[ast.expr]:
    """Yield *expr* and every sub-expression whose value flows into it.

    Only the containers and wrappers that carry a value through unchanged
    are followed: a call to something charmlint cannot see the body of
    might do anything to what it was passed, so its arguments are not
    reached. A call named in *sanitisers* ends the walk down that branch.
    """
    yield expr
    if isinstance(expr, ast.Call):
        target = _ast.call_target(expr, imports)
        if target in sanitisers:
            return
        if target in _TRANSPARENT_CALLS:
            for arg in expr.args:
                yield from _reachable(arg, imports, sanitisers)
        elif isinstance(expr.func, ast.Attribute) and expr.func.attr in _TRANSPARENT_METHODS:
            yield from _reachable(expr.func.value, imports, sanitisers)
            for arg in expr.args:
                yield from _reachable(arg, imports, sanitisers)
    elif isinstance(expr, ast.Dict):
        for value in expr.values:
            yield from _reachable(value, imports, sanitisers)
    elif isinstance(expr, ast.List | ast.Tuple):
        for element in expr.elts:
            yield from _reachable(element, imports, sanitisers)
    elif isinstance(expr, ast.JoinedStr):
        for part in expr.values:
            if isinstance(part, ast.FormattedValue):
                yield from _reachable(part.value, imports, sanitisers)
    elif isinstance(expr, ast.BinOp):
        yield from _reachable(expr.left, imports, sanitisers)
        yield from _reachable(expr.right, imports, sanitisers)


def _unordered_source(expr: ast.expr, imports: _ast.Imports) -> str | None:
    """Describe *expr* if it has no defined order, else ``None``."""
    if isinstance(expr, ast.Set | ast.SetComp):
        return "A set"
    if not isinstance(expr, ast.Call):
        return None
    target = _ast.call_target(expr, imports)
    if target in _UNORDERED_CALLS:
        return _UNORDERED_CALLS[target]
    if isinstance(expr.func, ast.Attribute):
        return _UNORDERED_METHODS.get(expr.func.attr)
    return None


def _nondeterministic_source(expr: ast.expr, imports: _ast.Imports) -> str | None:
    """Describe *expr* if it answers differently each call, else ``None``."""
    if not isinstance(expr, ast.Call):
        return None
    return _NONDETERMINISTIC_CALLS.get(_ast.call_target(expr, imports) or "")


def _unsorted_json_dump(expr: ast.expr, imports: _ast.Imports) -> str | None:
    """Describe *expr* if it is a ``json.dumps()`` that does not sort keys.

    A literal mapping is serialised in the order it is written, which is
    the same order every time, so only an argument charmlint cannot see
    the construction of is worth asking about.
    """
    if not isinstance(expr, ast.Call) or _ast.call_target(expr, imports) != "json.dumps":
        return None
    if _ast.keyword(expr, "sort_keys") is not None:
        return None
    argument = expr.args[0] if expr.args else None
    if argument is None or isinstance(argument, ast.Dict | ast.List | ast.Tuple | ast.Constant):
        return None
    # A sequence has no keys for ``sort_keys`` to order, so asking for it
    # would be noise; its own order is RELATIONS-003's question.
    if isinstance(argument, ast.Call) and _ast.call_target(argument, imports) in _SEQUENCE_CALLS:
        return None
    return "An unsorted JSON serialisation"
