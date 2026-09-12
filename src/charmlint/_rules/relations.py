"""Relation rules — what a charm writes into a relation databag.

Juju compares databag contents byte for byte, so a value whose textual
form changes between reconciliations without the underlying facts having
changed is republished as a change: the peer is woken with
``relation-changed``, republishes its own unstable data, and the two
charms flap. See `Your charm might be flapping its databags
<https://discourse.charmhub.io/t/your-charm-might-be-flapping-its-databags/20715>`_.
"""

import ast
from collections.abc import Iterator

from .. import _ast
from .. import _models as models
from ._base import Rule


class UnorderedValueInDatabag(Rule):
    """Flag an unordered collection written into a relation databag."""

    category = "RELATIONS"
    number = 3
    name = "unordered-value-in-databag"
    description = "Unordered collection written to a relation databag"
    default_severity = models.Severity.WARNING
    reference_url = (
        "https://discourse.charmhub.io/t/your-charm-might-be-flapping-its-databags/20715"
    )

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
            for path, line, reason in _findings(context)
        ]


# Callables whose result is as unstable as their argument, so the rule
# looks through them to what was passed in. ``json.dumps`` is one of
# them: ``sort_keys=True`` orders a mapping's keys and does nothing for
# the order of the list it was handed.
_TRANSPARENT_CALLS = frozenset(
    {"list", "tuple", "dict", "str", "repr", "json.dumps", "yaml.dump", "yaml.safe_dump"}
)

# Methods that reformat their receiver without reordering it, so the
# instability of ``",".join(x)`` is the instability of ``x``.
_TRANSPARENT_METHODS = frozenset(
    {"join", "format", "encode", "decode", "hex", "isoformat", "strftime"}
)

# Calls that settle an order, so nothing below them is unordered any more.
_ORDER_SANITISERS = frozenset({"sorted"})

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


def _findings(context: models.CharmContext) -> Iterator[tuple[str, int, str]]:
    """Yield ``(path, line, reason)`` for each unordered databag write."""
    for module in context.charm_sources():
        imports = _ast.Imports.of(module)
        for written in _databag_values(module):
            for expr in _reachable(written, imports):
                reason = _unordered_source(expr, imports)
                if reason is not None:
                    yield module.path, expr.lineno, reason
                    break


def _databag_values(module: models.Module) -> Iterator[ast.expr]:
    """Yield every expression written into a relation databag.

    ops models relation data as a mapping of mappings, so a write is
    recognised by that shape: ``<relation>.data[<entity>][<key>] = ...``
    for a single key, and ``<relation>.data[<entity>].update({...})`` for
    several at once. A charm just as often binds the databag to a local
    first, so a name assigned from one counts as a databag wherever else
    the module writes through it — about a third of the write sites in
    the charms charmlint has been measured against, and the shape both
    of the findings this rule has to its name.
    """
    aliases = _databag_aliases(module)
    for node in module.walk(ast.Assign, ast.AnnAssign, ast.Call):
        if isinstance(node, ast.Call):
            yield from _update_values(node, aliases)
            continue
        if node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(_is_databag_entry(target, aliases) for target in targets):
            yield node.value


def _databag_aliases(module: models.Module) -> frozenset[str]:
    """Return the names the module binds a whole databag to.

    Module-wide rather than per-scope: a name that means a databag in one
    method is not given a different meaning in the next, and the shape is
    specific enough that a collision would be a surprise.
    """
    return frozenset(
        target.id
        for node in module.walk(ast.Assign)
        if _is_databag(node.value)
        for target in node.targets
        if isinstance(target, ast.Name)
    )


def _update_values(call: ast.Call, aliases: frozenset[str]) -> Iterator[ast.expr]:
    """Yield the values a ``<databag>.update(...)`` call writes."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "update":
        return
    if not _is_databag(func.value) and not _is_alias(func.value, aliases):
        return
    for arg in call.args:
        if isinstance(arg, ast.Dict):
            yield from arg.values
    for keyword in call.keywords:
        # ``**other`` has no key of its own and nothing to look inside.
        if keyword.arg is not None:
            yield keyword.value


def _is_databag_entry(node: ast.expr, aliases: frozenset[str]) -> bool:
    """True for ``<relation>.data[<entity>][<key>]`` — one databag entry."""
    if not isinstance(node, ast.Subscript):
        return False
    return _is_databag(node.value) or _is_alias(node.value, aliases)


def _is_databag(node: ast.expr) -> bool:
    """True for ``<relation>.data[<entity>]`` — one whole databag."""
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "data"
    )


def _is_alias(node: ast.expr, aliases: frozenset[str]) -> bool:
    """True for a name the module bound a whole databag to."""
    return isinstance(node, ast.Name) and node.id in aliases


def _reachable(expr: ast.expr, imports: _ast.Imports) -> Iterator[ast.expr]:
    """Yield *expr* and every sub-expression whose value flows into it.

    Only the containers and wrappers that carry a value through unchanged
    are followed: a call charmlint cannot see the body of might sort what
    it was passed, so its arguments are not reached. A call that settles
    an order ends the walk down that branch.
    """
    yield expr
    if isinstance(expr, ast.Call):
        target = _ast.call_target(expr, imports)
        if target in _ORDER_SANITISERS:
            return
        if target in _TRANSPARENT_CALLS:
            for arg in expr.args:
                yield from _reachable(arg, imports)
        elif isinstance(expr.func, ast.Attribute) and expr.func.attr in _TRANSPARENT_METHODS:
            yield from _reachable(expr.func.value, imports)
            for arg in expr.args:
                yield from _reachable(arg, imports)
    elif isinstance(expr, ast.Dict):
        for value in expr.values:
            yield from _reachable(value, imports)
    elif isinstance(expr, ast.List | ast.Tuple):
        for element in expr.elts:
            yield from _reachable(element, imports)
    elif isinstance(expr, ast.JoinedStr):
        for part in expr.values:
            if isinstance(part, ast.FormattedValue):
                yield from _reachable(part.value, imports)
    elif isinstance(expr, ast.BinOp):
        yield from _reachable(expr.left, imports)
        yield from _reachable(expr.right, imports)


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
