"""Performance rules — avoidable runtime cost in a charm's Python source."""

import ast
import dataclasses
from collections.abc import Iterator, Sequence

from .. import _ast
from .. import _models as models
from ._base import Rule

# The two ``ops.Container`` methods that read Pebble state and are cheap to
# hoist: both return a snapshot that stays valid until something changes it.
# ``get_plan`` takes no arguments, ``get_service`` takes the service name.
_READS = frozenset({"get_plan", "get_service"})

# Container methods that change what a read would return. A read after one
# of these is re-reading what was just written, which is correct rather than
# wasteful, so a mutation ends the run of reads it sits in.
#
# Only ``add_layer`` changes the plan: ``replan`` and the start/stop family
# act on the services the plan already describes, so they invalidate
# ``get_service`` — which reports a service's live status — and leave
# ``get_plan`` alone.
_SERVICE_MUTATIONS = frozenset(
    {
        "add_layer",
        "replan",
        "autostart",
        "start",
        "stop",
        "restart",
        "start_services",
        "stop_services",
        "restart_services",
        "send_signal",
    }
)
_PLAN_MUTATIONS = frozenset({"add_layer"})

# charmlint has no type inference, so a Pebble container is recognised by
# what the variable holding it is called, the same heuristic that
# ``_ast.receiver`` documents. ``get_service`` in particular is a common
# method name on unrelated API clients, and one of those was the only thing
# this rule found in the charm corpus before the guard was added.
_CONTAINER_HINTS = ("container", "workload")


def _invalidated_by(method: str) -> frozenset[str]:
    """Return the read methods a call to *method* on a container invalidates."""
    invalidated: set[str] = set()
    if method in _PLAN_MUTATIONS:
        invalidated.add("get_plan")
    if method in _SERVICE_MUTATIONS:
        invalidated.add("get_service")
    return frozenset(invalidated)


def _is_container(receiver: str) -> bool:
    """Whether *receiver* names something that looks like a Pebble container."""
    trailing = receiver.rsplit(".", 1)[-1].lower()
    return any(hint in trailing for hint in _CONTAINER_HINTS)


# Statement fields holding a nested statement list. Walked by the traversal
# below rather than by the expression scan, so a call is attributed to the
# statement that actually contains it.
_BODY_FIELDS = frozenset({"body", "orelse", "finalbody", "handlers", "cases"})


@dataclasses.dataclass(frozen=True)
class _Event:
    """One Pebble call on a named receiver, in the function that holds it.

    ``key`` identifies what was read — ``("get_plan", "")`` or
    ``("get_service", "<name>")``. ``invalidates`` is empty for a read, and
    for anything else names the reads it makes stale: a mutating method
    invalidates what it changes, and a reassignment of a name invalidates
    every read that mentions it.

    ``branch`` is the chain of conditional branches the call sits in, used
    to tell two calls that both run from two that are alternatives.
    """

    receiver: str
    key: tuple[str, str]
    invalidates: frozenset[str]
    branch: tuple[tuple[int, int], ...]
    node: ast.stmt | ast.expr

    @property
    def read(self) -> bool:
        """Whether this event reads Pebble state rather than disturbing it."""
        return not self.invalidates


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


def _read_key(call: ast.Call) -> tuple[str, str] | None:
    """Return the read this call performs, or ``None`` if it is not one.

    The second element is the service name *as the source spells it*, which
    is what makes two calls comparable. A string literal is kept quoted and
    a name is not, so ``get_service(SERVICE)`` and ``get_service('SERVICE')``
    stay distinct. Charms overwhelmingly name the service with a module
    constant or an enum member rather than a literal, so a rule that only
    understood literals would miss nearly every real case.

    Anything else — an f-string, a subscript, a call — is not comparable
    and yields ``None``.
    """
    method = call.func.attr if isinstance(call.func, ast.Attribute) else None
    if method not in _READS or call.keywords:
        return None
    if method == "get_plan":
        return ("get_plan", "") if not call.args else None
    if len(call.args) != 1:
        return None
    argument = call.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return ("get_service", repr(argument.value))
    spelling = _ast.dotted_name(argument)
    return ("get_service", spelling) if spelling is not None else None


def _rebinds(statement: ast.stmt) -> set[str]:
    """Return the names *statement* assigns to.

    A receiver that is reassigned may be a different container afterwards,
    and a service name that is reassigned may name a different service, so
    an assignment ends the run of reads the same way a mutation does.
    """
    if isinstance(statement, ast.Assign):
        targets: Sequence[ast.expr] = statement.targets
    elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
        targets = [statement.target]
    else:
        return set()
    return {name for name in (_ast.dotted_name(t) for t in targets) if name is not None}


def _events(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[_Event]:
    """Return every Pebble read, mutation and rebind in *function*, in order.

    Ordering is by source position, which is what the run-splitting below
    needs: a mutation only excuses the reads that come after it.
    """
    found: list[_Event] = []
    for statement, branch in _walk_body(function.body, ()):
        for name in _rebinds(statement):
            found.append(_Event(name, ("", ""), frozenset(_READS), branch, statement))
        for node in _expressions(statement):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = _ast.dotted_name(node.func.value)
            if receiver is None or not _is_container(receiver):
                # An unreadable receiver — a call or a subscript in the chain
                # — gives nothing to compare two spellings by, and one that is
                # not named like a container is assumed not to be one.
                continue
            key = _read_key(node)
            if key is not None:
                found.append(_Event(receiver, key, frozenset(), branch, node))
                continue
            invalidates = _invalidated_by(node.func.attr)
            if invalidates:
                found.append(_Event(receiver, ("", ""), invalidates, branch, node))
    found.sort(key=lambda event: (event.node.lineno, event.node.col_offset))
    return found


def _describe(receiver: str, key: tuple[str, str]) -> str:
    """Spell the repeated call the way the source did."""
    method, argument = key
    if method == "get_plan":
        return f"{receiver}.get_plan()"
    return f"{receiver}.get_service({argument})"


class RepeatedPebbleState(Rule):
    """Detect the same Pebble state read made twice in one function.

    ``container.get_plan()`` and ``container.get_service(name)`` each open a
    connection to pebbled over the workload's unix socket and wait for the
    reply. Making the same call twice in a function does the round trip
    twice for a result that has not changed in between; storing it in a
    local is both faster and easier to read.

    Three things stop a repeat from being reported, because in each case the
    second call is not redundant: a change to the same container between the
    two that affects what is read (``add_layer`` for the plan, that plus the
    start/stop family for a service), a reassignment of the receiver or of
    the service name between them, and the two calls sitting in alternative
    branches of the same ``if`` or ``match``, where only one of them runs.

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
    reference_url = "https://documentation.ubuntu.com/ops/latest/reference/pebble/"

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
        pending: dict[tuple[str, tuple[str, str]], list[_Event]] = {}
        for event in _events(function):
            if not event.read:
                # A write to the container invalidates what was read from it;
                # a write to the name a service was looked up by makes two
                # calls that read alike no longer the same lookup.
                stale = [
                    k
                    for k in pending
                    if event.receiver in (k[0], k[1][1]) and k[1][0] in event.invalidates
                ]
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
