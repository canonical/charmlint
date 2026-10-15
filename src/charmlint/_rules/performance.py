"""Performance rules — avoidable runtime cost in a charm's Python source."""

import ast
import dataclasses
from collections.abc import Iterator, Sequence

from .. import _ast
from .. import _models as models
from ._base import Rule

# The ``ops.Container`` methods that read Pebble state. Each returns a
# snapshot that stays valid until something changes it, so a second
# identical call in the same function is a second round trip for the same
# answer.
_PLAN_READS = frozenset({"get_plan"})
_SERVICE_READS = frozenset({"get_services", "get_service"})
_CHECK_READS = frozenset({"get_checks", "get_check"})
_READS = _PLAN_READS | _SERVICE_READS | _CHECK_READS

# Each read's signature on ``ops.Container``: how many arguments it takes
# (``None`` for any number of positional ones), and the keyword names it
# accepts. A call that doesn't fit is some other object's method of the
# same name.
_SIGNATURES: dict[str, tuple[int | None, frozenset[str]]] = {
    "get_plan": (0, frozenset()),
    "get_services": (None, frozenset()),
    "get_service": (1, frozenset({"service_name"})),
    "get_checks": (None, frozenset({"level"})),
    "get_check": (1, frozenset({"check_name"})),
}

# Container methods that change what a read would return, mapped to the
# reads they make stale. A read after one of these is re-reading what was
# just written, which is correct rather than wasteful, so a mutation ends
# the run of reads it sits in.
#
# ``add_layer`` changes the plan, and with it the services and checks the
# plan describes. ``replan`` and the start/stop family act on services the
# plan already has, so they leave ``get_plan`` alone. ``replan`` also
# starts and stops checks, as do ``start_checks`` and ``stop_checks``.
_INVALIDATES: dict[str, frozenset[str]] = {
    "add_layer": _READS,
    "replan": _SERVICE_READS | _CHECK_READS,
    "autostart": _SERVICE_READS,
    "start": _SERVICE_READS,
    "stop": _SERVICE_READS,
    "restart": _SERVICE_READS,
    "send_signal": _SERVICE_READS,
    "start_checks": _CHECK_READS,
    "stop_checks": _CHECK_READS,
}

# charmlint has no type inference, so a Pebble container is recognised by
# what the variable holding it is called, the same heuristic that
# ``_ast.receiver`` documents. ``get_service`` in particular is a common
# method name on unrelated API clients, and one of those was the only thing
# this rule found in the charm corpus before the guard was added.
_CONTAINER_HINTS = ("container", "workload")


def _is_container(receiver: str) -> bool:
    """Whether *receiver* names something that looks like a Pebble container."""
    trailing = receiver.rsplit(".", 1)[-1].lower()
    return any(hint in trailing for hint in _CONTAINER_HINTS)


# Statement fields holding a nested statement list. Walked by the traversal
# below rather than by the expression scan, so a call is attributed to the
# statement that actually contains it. Wider than ``_ast._BODY_FIELDS``
# because the expression scan has to skip every nested list, including the
# ``except`` handlers and ``match`` cases that ``_ast`` reaches separately.
_BODY_FIELDS = frozenset({"body", "orelse", "finalbody", "handlers", "cases"})


# What a read looked up: the method, and its arguments as the source spells
# them.
_Key = tuple[str, tuple[str, ...]]


@dataclasses.dataclass(frozen=True)
class _Event:
    """One Pebble read, or one thing that makes earlier reads stale.

    A read has a ``key``: the method and its arguments, such as
    ``("get_service", ("'app'",))``. Anything else has ``key`` set to
    ``None`` and ``invalidates`` naming the read methods it makes stale. A
    mutating container method invalidates what it changes. A reassignment
    of a name, or a call that might change a container out of sight,
    invalidates every read that mentions the name.

    ``branch`` is the chain of conditional branches the call sits in, used
    to tell two calls that both run from two that are alternatives.
    """

    receiver: str
    key: _Key | None
    invalidates: frozenset[str]
    branch: tuple[tuple[int, int], ...]
    node: ast.stmt | ast.expr

    def makes_stale(self, receiver: str, key: _Key) -> bool:
        """Whether this event makes a read of *key* on *receiver* stale."""
        if key[0] not in self.invalidates:
            return False
        return any(_names_within(self.receiver, name) for name in (receiver, *key[1]))


def _names_within(name: str, spelling: str) -> bool:
    """Whether *spelling* is *name* or an attribute reached through it."""
    return spelling == name or spelling.startswith(f"{name}.")


def _branches_exclude(left: _Event, right: _Event) -> bool:
    """Whether *left* and *right* are in alternative branches of one ``if``.

    Two calls in the arms of the same ``if`` — or in different cases of the
    same ``match`` — never both run, so repeating a call across them costs
    nothing. Anything else (a ``try`` body and its handler, two separate
    ``if`` statements) is treated as reachable together, which is the
    conservative reading for a rule that would rather miss than misreport.
    """
    for outer, inner in zip(left.branch, right.branch, strict=False):
        if outer[0] == inner[0] and outer[1] != inner[1]:
            return True
    return False


def _expressions(statement: ast.stmt) -> Iterator[ast.AST]:
    """Yield the expression nodes belonging to *statement* itself.

    Nested statement lists are skipped: they are reached by the traversal,
    so an ``if`` contributes its test here and its branches there.
    """
    for field, value in ast.iter_fields(statement):
        if field in _BODY_FIELDS:
            continue
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, ast.AST):
                yield from ast.walk(item)


def _walk_body(
    body: Sequence[ast.stmt], branch: tuple[tuple[int, int], ...]
) -> Iterator[tuple[ast.stmt, tuple[tuple[int, int], ...]]]:
    """Yield each statement reachable in *body*, with its branch chain.

    Unlike :func:`_ast.walk_statements`, this stops at a nested function or
    class: those statements do not run in the enclosing function, and
    counting them there would report a call made once per call of the inner
    function as a repeat. Each nested definition is walked in its own right
    when the module's function list reaches it.
    """
    for statement in body:
        yield statement, branch
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(statement, ast.If):
            # The arms of one ``if`` are alternatives; number them so a call
            # in each can be recognised as such.
            yield from _walk_body(statement.body, (*branch, (id(statement), 0)))
            yield from _walk_body(statement.orelse, (*branch, (id(statement), 1)))
            continue
        if isinstance(statement, ast.Match):
            for index, case in enumerate(statement.cases):
                yield from _walk_body(case.body, (*branch, (id(statement), index)))
            continue
        for field in ("body", "orelse", "finalbody"):
            nested = getattr(statement, field, None)
            if isinstance(nested, list):
                yield from _walk_body(nested, branch)
        for handler in getattr(statement, "handlers", []):
            yield from _walk_body(handler.body, branch)


def _spell(argument: ast.expr) -> str | None:
    """Spell an argument the way the source did, or ``None`` if it can't be compared.

    A string literal is kept quoted and a name is not, so
    ``get_service(SERVICE)`` and ``get_service('SERVICE')`` stay distinct.
    Charms overwhelmingly name the service with a module constant or an
    enum member rather than a literal, so a rule that only understood
    literals would miss nearly every real case. Anything else, such as an
    f-string, a subscript, or a call, is not comparable.
    """
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return repr(argument.value)
    return _ast.dotted_name(argument)


def _read_key(call: ast.Call) -> _Key | None:
    """Return the read this call performs, or ``None`` if it is not a comparable one.

    A read with an argument that can't be compared yields ``None`` too, and
    so records no event. That is safe because a read never makes another
    read stale: only a mutation, a rebind, or an opaque call does.
    """
    method = call.func.attr if isinstance(call.func, ast.Attribute) else None
    if method not in _READS:
        return None
    count, keywords = _SIGNATURES[method]
    if any(keyword.arg not in keywords for keyword in call.keywords):
        return None
    if count is not None and len(call.args) + len(call.keywords) != count:
        return None
    spellings = [_spell(argument) for argument in call.args]
    spellings += [
        None if (value := _spell(keyword.value)) is None else f"{keyword.arg}={value}"
        for keyword in call.keywords
    ]
    if None in spellings:
        return None
    return (method, tuple(s for s in spellings if s is not None))


def _rebinds(statement: ast.stmt) -> set[str]:
    """Return the names *statement* assigns to.

    A receiver that is reassigned may be a different container afterwards,
    and a service name that is reassigned may name a different service, so
    an assignment ends the run of reads the same way a mutation does. Every
    way of binding a name counts: ``=``, ``for`` targets, ``with ... as``,
    ``:=``, and tuple unpacking all store to it.
    """
    return {
        name
        for node in _expressions(statement)
        if isinstance(node, ast.Name | ast.Attribute) and isinstance(node.ctx, ast.Store)
        for name in (_ast.dotted_name(node),)
        if name is not None
    }


def _hidden_mutations(call: ast.Call) -> set[str]:
    """Return the names whose container *call* might change out of sight.

    The rule only looks inside one function, so a helper that pushes a
    layer is invisible: ``self._push_layer(container)`` between two
    ``container.get_plan()`` calls makes the second read necessary. With
    no way to look inside the helper, a call that is handed a container,
    or a method call on ``self`` (which can reach ``self._container``), is
    assumed to change it. That costs some true positives, which is the
    right trade for an informational rule.
    """
    names: set[str] = set()
    for argument in (*call.args, *(keyword.value for keyword in call.keywords)):
        name = _ast.dotted_name(argument)
        if name is not None and (name == "self" or _is_container(name)):
            names.add(name)
    if (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "self"
    ):
        names.add("self")
    return names


def _events(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[_Event]:
    """Return every Pebble read, mutation and rebind in *function*, in order.

    Ordering is by source position, which is what the run-splitting below
    needs: a mutation only excuses the reads that come after it.
    """
    found: list[_Event] = []
    for statement, branch in _walk_body(function.body, ()):
        for name in _rebinds(statement):
            found.append(_Event(name, None, _READS, branch, statement))
        for node in _expressions(statement):
            if not isinstance(node, ast.Call):
                continue
            for name in _hidden_mutations(node):
                found.append(_Event(name, None, _READS, branch, node))
            if not isinstance(node.func, ast.Attribute):
                continue
            receiver = _ast.dotted_name(node.func.value)
            if receiver is None or not _is_container(receiver):
                # An unreadable receiver (a call or a subscript in the chain)
                # gives nothing to compare two spellings by, and one that is
                # not named like a container is assumed not to be one.
                continue
            key = _read_key(node)
            if key is not None:
                found.append(_Event(receiver, key, frozenset(), branch, node))
                continue
            invalidates = _INVALIDATES.get(node.func.attr)
            if invalidates:
                found.append(_Event(receiver, None, invalidates, branch, node))
    found.sort(key=lambda event: (event.node.lineno, event.node.col_offset))
    return found


def _describe(receiver: str, key: _Key) -> str:
    """Spell the repeated call the way the source did."""
    method, arguments = key
    return f"{receiver}.{method}({', '.join(arguments)})"


class RepeatedPebbleState(Rule):
    """Detect the same Pebble state read made twice in one function.

    ``container.get_plan()``, ``get_services()``, ``get_service(name)``,
    ``get_checks()`` and ``get_check(name)`` each open a connection to
    pebbled over the workload's unix socket and wait for the reply. Making
    the same call twice in a function does the round trip twice for a
    result that has not changed in between; storing it in a local is both
    faster and easier to read.

    A repeat is not reported when the second call is not redundant:

    * Something between the two changes what is read: ``add_layer`` for
      the plan, that plus ``replan`` and the start/stop family for
      services, and ``replan`` and ``start_checks``/``stop_checks`` for
      checks.
    * The receiver or an argument is rebound between them, by any form of
      assignment.
    * A call between them might change the container where the rule can't
      see: one that is handed the container, or a method call on ``self``
      when the container is reached through ``self``.
    * The two calls sit in alternative branches of the same ``if`` or
      ``match``, so only one of them runs.

    The container is recognised by what it is called, so a repeat on a
    variable not named like a container is left alone. ``get_service`` is a
    common method name elsewhere, and with no type information the name is
    all there is to go on.
    """

    category = "PERFORMANCE"
    number = 2
    name = "repeated-pebble-state"
    description = "The same Pebble state read is made more than once in one function"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/ops/latest/reference/pebble/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            for function in module.functions():
                diagnostics.extend(self._check_function(function, module.path))
        return diagnostics

    def _check_function(
        self, function: ast.FunctionDef | ast.AsyncFunctionDef, path: str
    ) -> list[models.Diagnostic]:
        """Report each read repeated within one run of *function*."""
        diagnostics: list[models.Diagnostic] = []
        # Reads still standing for each (receiver, key), cleared whenever the
        # receiver is written to.
        pending: dict[tuple[str, _Key], list[_Event]] = {}
        for event in _events(function):
            if event.key is None:
                # A write to the container invalidates what was read from it;
                # a write to the name a service was looked up by makes two
                # calls that read alike no longer the same lookup.
                stale = [k for k in pending if event.makes_stale(*k)]
                for key in stale:
                    del pending[key]
                continue
            seen = pending.setdefault((event.receiver, event.key), [])
            earlier = next((e for e in seen if not _branches_exclude(e, event)), None)
            if earlier is not None:
                diagnostics.append(
                    self.diagnostic(
                        f"{_describe(event.receiver, event.key)} is called again in "
                        f"'{function.name}' (first at line {earlier.node.lineno}) "
                        f"— each call is a round trip to pebbled",
                        path=path,
                        line=event.node.lineno,
                        fix_hint=(
                            "Store the result in a local variable and reuse it, or "
                            "re-read it only after changing the container"
                        ),
                    )
                )
            seen.append(event)
        return diagnostics
