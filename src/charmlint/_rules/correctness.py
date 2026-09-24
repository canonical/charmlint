"""Correctness rules — runtime-correctness issues in charm source."""

import ast
import dataclasses
from collections.abc import Callable, Iterator

from .. import _ast
from .. import _models as models
from ._base import Rule


class DeferWithoutReturn(Rule):
    """Flag ``event.defer()`` not immediately followed by ``return``."""

    category = "CORRECTNESS"
    number = 1
    name = "defer-without-return"
    description = "event.defer() not immediately followed by return"
    default_severity = models.Severity.WARNING
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
                    if not self._database_ready():
                        event.defer()
                    self._replan()
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
                    if not self._database_ready():
                        event.defer()
                        return
                    self._replan()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        def is_non_return(following: ast.stmt | None) -> bool:
            # A following `raise` is a defer that never persists; that case
            # is reported by CORRECTNESS-002, so exclude it here rather than
            # emit a second diagnostic on the same line.
            return following is not None and not isinstance(following, ast.Return | ast.Raise)

        return [
            self.diagnostic(
                "event.defer() is not immediately followed by "
                "`return` — the handler keeps "
                "executing after deferring, so any subsequent "
                "side effects run both now and on the "
                "deferred retry",
                path=path,
                line=line,
                fix_hint=(
                    "Add `return` immediately after "
                    "`event.defer()` so the handler exits "
                    "cleanly and the deferred retry is the "
                    "only execution that performs follow-up "
                    "work"
                ),
            )
            for path, line in _find_defers_followed_by(context, match_next=is_non_return)
        ]


class DeferBeforeRaise(Rule):
    """Flag ``event.defer()`` immediately followed by ``raise``.

    An uncaught exception during a hook aborts the framework commit, so
    the ``defer()`` never persists — the event will not be re-emitted.
    Either raise without deferring (if the failure should propagate) or
    defer and return (if the event should be retried).
    """

    category = "CORRECTNESS"
    number = 2
    name = "defer-before-raise"
    description = "event.defer() immediately followed by raise"
    default_severity = models.Severity.WARNING
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _on_config_changed(self, event: ops.ConfigChangedEvent):
                    if not self._container.can_connect():
                        event.defer()
                        raise RuntimeError("workload container not ready")
                    self._replan()
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _on_config_changed(self, event: ops.ConfigChangedEvent):
                    if not self._container.can_connect():
                        event.defer()
                        return
                    self._replan()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        def is_raise(following: ast.stmt | None) -> bool:
            return isinstance(following, ast.Raise)

        return [
            self.diagnostic(
                "event.defer() is immediately followed by "
                "`raise` — the exception aborts the framework "
                "commit, so the defer never persists and the "
                "event will not be re-emitted",
                path=path,
                line=line,
                fix_hint=(
                    "Either drop the `event.defer()` (if the "
                    "failure should propagate) or replace the "
                    "`raise` with `return` (if the event "
                    "should be retried)"
                ),
            )
            for path, line in _find_defers_followed_by(context, match_next=is_raise)
        ]


class ExecResultNotConsumed(Rule):
    """Flag bare ``container.exec(...)`` calls whose result is discarded.

    A bare ``container.exec(...)`` starts the process but never waits for it,
    never captures its exit code, and can stall the container if stdout or
    stderr fills the pipe buffer. The result must either be assigned (so the
    caller can ``.wait()`` / ``.wait_output()`` later) or chained directly,
    e.g. ``container.exec(...).wait_output()``.
    """

    category = "CORRECTNESS"
    number = 3
    name = "exec-result-not-consumed"
    description = "container.exec() result not consumed (no .wait() / .wait_output())"
    default_severity = models.Severity.ERROR
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _migrate(self):
                    container = self.unit.get_container("frontend")
                    container.exec(["frontend", "migrate"])
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _migrate(self):
                    container = self.unit.get_container("frontend")
                    container.exec(["frontend", "migrate"]).wait_output()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            for node in module.walk(ast.Expr):
                # Only bare expression statements are problematic. A chained
                # ``.wait()`` parses as ``Call(func=Attribute(attr='wait',
                # value=Call(attr='exec', ...)))`` — the outer Expr.value is
                # the wait call, not the exec call — so matching on the
                # statement's own call naturally skips chained calls.
                call = node.value
                if not isinstance(call, ast.Call):
                    continue
                target = _ast.call_target(call)
                if target is None or not target.endswith(".exec"):
                    continue
                # Only ops.Container.exec() (Pebble) is non-blocking and needs a
                # trailing .wait*(). Charms conventionally name that receiver
                # ``container`` (e.g. ``container``, ``self.container``,
                # ``self._container``). The data-platform ``WorkloadBase.exec()``
                # wrapper — ``self.workload.exec(...)``, ``self.exec(...)`` — blocks
                # internally (subprocess, or an internal ``.wait_output()``) and
                # returns a str, so discarding its result is correct. Gating on the
                # receiver name keeps those wrappers from being flagged. This can
                # miss a container bound to an unconventional name, but that trade
                # avoids a large volume of false positives on the wrapper idiom.
                name = _ast.receiver(call)
                if name is None:
                    continue
                lname = name.lower()
                if not (lname == "container" or lname.endswith("_container")):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "container.exec() result not consumed — the process runs "
                        "asynchronously, no exit code is checked, and a full "
                        "stdout/stderr buffer can stall the container",
                        path=module.path,
                        line=call.lineno,
                        fix_hint=(
                            "Chain `.wait()` or `.wait_output()` on the call, "
                            "or assign the result and call `.wait*()` on it later"
                        ),
                    )
                )
        return diagnostics


def _find_defers_followed_by(
    context: models.CharmContext,
    match_next: Callable[[ast.stmt | None], bool],
) -> list[tuple[str, int]]:
    """Find each ``event.defer()`` whose continuation matches ``match_next``.

    ``match_next`` receives the statement that executes immediately after
    the ``event.defer()`` — its next sibling in the same block, or, when the
    ``defer()`` is the last statement in its block, whatever runs once that
    block completes (``None`` if control then leaves the function/module).
    Returns ``(path, lineno)`` for each matching ``event.defer()``.
    """
    return [
        (str(module.file), statement.lineno)
        for module in context.charm_sources()
        for statement, following in _ast.walk_statements(module.tree.body)
        if _is_event_defer(statement) and match_next(following)
    ]


def _is_event_defer(node: ast.AST) -> bool:
    """True if ``node`` is the statement ``event.defer()``."""
    if not isinstance(node, ast.Expr):
        return False
    call = node.value
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "defer"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "event"
        and not call.args
        and not call.keywords
    )


# Events whose `defer()` raises RuntimeError. `stop`, `remove`,
# `secret-expired` and `secret-rotate` override `defer()` in `ops.charm`;
# `pre-commit`, `commit`, `collect-unit-status` and `collect-app-status`
# are `LifecycleEvent`s, which raise from the base override in
# `ops.framework`. Action events are handled separately, by suffix.
_NON_DEFERRABLE_EVENTS = frozenset(
    {
        "stop",
        "remove",
        "secret_expired",
        "secret_rotate",
        "pre_commit",
        "commit",
        "collect_unit_status",
        "collect_app_status",
    }
)


def _is_non_deferrable(event: str) -> bool:
    """Whether ops raises from ``defer()`` on the event named *event*."""
    return event in _NON_DEFERRABLE_EVENTS or event.endswith("_action")


def _non_deferrable_handlers(module: models.Module) -> dict[str, list[str]]:
    """Map handler method name -> non-deferrable events it is registered for.

    One handler can be observed for several events, so every non-deferrable
    one is kept: a ``defer()`` in the handler raises for all of them.
    """
    handlers: dict[str, list[str]] = {}
    for observer in _ast.observers(module):
        if observer.event is None or observer.handler is None:
            continue
        if _is_non_deferrable(observer.event):
            handlers.setdefault(observer.handler, []).append(observer.event)
    return handlers


def _defer_calls(func: ast.FunctionDef | ast.AsyncFunctionDef, event: str) -> list[ast.Call]:
    """Return every ``<event>.defer()`` call in *func*, in walk order.

    Nested function definitions are walked as well: a ``defer()`` inside a
    closure still runs as part of the handler.
    """
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and not node.args
        and not node.keywords
        and _ast.call_target(node) == f"{event}.defer"
    ]


class NonDeferrableEventDeferred(Rule):
    """Flag ``event.defer()`` inside a handler for a non-deferrable event.

    Only handlers registered as ``self.<handler>`` in a
    ``framework.observe(...)`` call are matched, and only ``defer()`` on a
    plain local name (the handler's event argument) counts — deferring a
    *different* event that was stashed on ``self`` isn't this bug.

    A handler observing both a deferrable and a non-deferrable event is
    still flagged: the ``defer()`` raises whenever the non-deferrable
    event is the one being dispatched.
    """

    category = "CORRECTNESS"
    number = 4
    name = "non-deferrable-event-deferred"
    description = "event.defer() called in a handler for a non-deferrable event"
    default_severity = models.Severity.ERROR
    reference_url = (
        "https://canonical.com/juju/docs/ops/latest/explanation/defer-guidance/"
        "#not-possible-actions-shutting-down-framework-generated-events-secrets"
    )
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.stop, self._on_stop)

                def _on_stop(self, event: ops.StopEvent):
                    if not self._drained():
                        event.defer()
                        return
                    self._shutdown()
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.stop, self._on_stop)

                def _on_stop(self, event: ops.StopEvent):
                    self._drain()
                    self._shutdown()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            diagnostics.extend(self._check_module(module))
        return diagnostics

    def _check_module(self, module: models.Module) -> list[models.Diagnostic]:
        handlers = _non_deferrable_handlers(module)
        if not handlers:
            return []
        diagnostics: list[models.Diagnostic] = []
        # `handlers` was built from the module's observe calls; walk the
        # module's functions to find the ones those calls named.
        for func in module.functions():
            if func.name not in handlers:
                continue
            events = handlers[func.name]
            # The event argument is the handler's second parameter; a
            # `defer()` on any other local name is a different object.
            params = [arg.arg for arg in func.args.args]
            if len(params) < 2:
                continue
            event_param = params[1]
            pretty = ", ".join(f"'{event.replace('_', '-')}'" for event in events)
            for call in _defer_calls(func, event_param):
                diagnostics.append(
                    self.diagnostic(
                        f"'{func.name}' calls {event_param}.defer(), but is registered for "
                        f"{pretty}, which cannot be deferred — this raises RuntimeError "
                        f"at runtime",
                        path=module.path,
                        line=call.lineno,
                        fix_hint=(
                            "Remove the defer() call: handle the condition inline, retry "
                            "briefly, or (for actions) fail the action with a message"
                        ),
                    )
                )
        return diagnostics


# The events ``ops.CharmEvents`` declares for every charm, whatever its
# metadata says. Kept as literals rather than read from an installed ops:
# charmlint lints a charm it does not import, and the charm's ops version
# is not charmlint's.
_LIFECYCLE_EVENTS = frozenset(
    {
        "install",
        "start",
        "stop",
        "remove",
        "update_status",
        "config_changed",
        "upgrade_charm",
        "pre_series_upgrade",
        "post_series_upgrade",
        "leader_elected",
        "leader_settings_changed",
        "collect_metrics",
        "secret_changed",
        "secret_expired",
        "secret_rotate",
        "secret_remove",
        "collect_app_status",
        "collect_unit_status",
    }
)

# The per-name events ``CharmBase.__init__`` defines from the charm's
# metadata, as ``<name><suffix>``. Each entry gives the suffix, the
# metadata section the name has to be declared in, and how to describe
# that declaration in a fix hint.
_METADATA_EVENTS: tuple[tuple[str, str, str], ...] = (
    ("_relation_created", "relations", "an endpoint under `provides:`, `requires:` or `peers:`"),
    ("_relation_joined", "relations", "an endpoint under `provides:`, `requires:` or `peers:`"),
    ("_relation_changed", "relations", "an endpoint under `provides:`, `requires:` or `peers:`"),
    ("_relation_departed", "relations", "an endpoint under `provides:`, `requires:` or `peers:`"),
    ("_relation_broken", "relations", "an endpoint under `provides:`, `requires:` or `peers:`"),
    ("_storage_attached", "storage", "a storage under `storage:`"),
    ("_storage_detaching", "storage", "a storage under `storage:`"),
    ("_pebble_ready", "containers", "a container under `containers:`"),
    ("_pebble_custom_notice", "containers", "a container under `containers:`"),
    ("_pebble_check_failed", "containers", "a container under `containers:`"),
    ("_pebble_check_recovered", "containers", "a container under `containers:`"),
    ("_action", "actions", "an action under `actions:`"),
)

_CHARM_BASES = frozenset({"ops.CharmBase", "ops.charm.CharmBase"})
_CHARM_EVENTS_BASES = frozenset({"ops.CharmEvents", "ops.charm.CharmEvents"})
_EVENT_SOURCE = frozenset({"ops.EventSource", "ops.framework.EventSource"})


def _names(section: models.Yaml) -> set[str]:
    """Return the underscored declared names in a metadata section.

    Juju spells endpoint, storage, container and action names with
    hyphens; ops replaces them with underscores when it defines the
    events, so that is the form to compare against. A key YAML did not
    construct as a string (an unquoted ``on:`` is the boolean ``True``
    under YAML 1.1) is not a name any of these sections can use.
    """
    return {key.replace("-", "_") for key in section if isinstance(key, str)}


def _base_names(node: ast.ClassDef, imports: _ast.Imports) -> list[str | None]:
    """Return each base of *node*, resolved through *imports*.

    An entry is ``None`` for a base that is not a plain name chain — a
    subscripted generic, say — which is a base this rule cannot identify.
    """
    return [imports.resolve(base) for base in node.bases]


def _custom_event_names(context: models.CharmContext) -> tuple[set[str], bool]:
    """Return the event names the charm's own code defines, and whether that is all.

    Two ways a charm adds an event to ``self.on``: an ``EventSource`` on
    a ``CharmEvents`` subclass, or a ``define_event`` call. Both are
    swept for over the *whole* charm, vendored libraries included — an
    event a library defines is as real as one the charm defines, and
    over-collecting here only ever makes the rule quieter.

    The flag is ``False`` when a ``define_event`` call was found whose
    name could not be read statically (``f"{alias}_database_created"``,
    the data-platform libraries' idiom). The charm then has events this
    rule cannot name, so no event name can be called impossible —
    ``self.on`` is the same object throughout a charm, and there is no
    telling from a call site which object a library's ``self.on`` was.
    Handler names are unaffected, so that half of the rule still runs.
    """
    found: set[str] = set()
    complete = True
    for module in context.modules():
        imports = _ast.Imports.of(module)
        for node in module.walk(ast.ClassDef):
            if not _CHARM_EVENTS_BASES.intersection(
                base for base in _base_names(node, imports) if base
            ):
                continue
            found.update(_event_sources(node, imports))
        for call in module.walk(ast.Call):
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "define_event"):
                continue
            name = _ast.dict_key(call.args[0]) if call.args else None
            if name is None:
                complete = False
            else:
                found.add(name)
    return found, complete


def _event_sources(node: ast.ClassDef, imports: _ast.Imports) -> Iterator[str]:
    """Yield the ``x = EventSource(...)`` attribute names declared in *node*."""
    for statement in node.body:
        if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
            continue
        if imports.resolve(statement.value.func) not in _EVENT_SOURCE:
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name):
                yield target.id


def _on_receiver(expr: ast.expr) -> str | None:
    """Return the object an observed event hangs off, e.g. ``"self"``.

    ``self.on.config_changed`` and ``self.on['db'].relation_changed`` both
    give ``"self"``; ``self.database.on.database_created`` gives
    ``"self.database"``, which is a library's own event source rather than
    the charm's. Returns ``None`` when the expression is not an event
    reference this rule recognises.
    """
    if isinstance(expr, ast.Call):
        # getattr(self.on, '<event>')
        target = expr.args[0] if expr.args else None
        if isinstance(target, ast.Attribute) and target.attr == "on":
            return _ast.dotted_name(target.value)
        return None
    if not isinstance(expr, ast.Attribute):
        return None
    parent = expr.value
    if isinstance(parent, ast.Subscript):
        parent = parent.value
    if isinstance(parent, ast.Attribute) and parent.attr == "on":
        return _ast.dotted_name(parent.value)
    return None


@dataclasses.dataclass(frozen=True)
class _CharmClass:
    """A charm class, with what its ``observe`` calls can legitimately name."""

    node: ast.ClassDef
    # Every name that could answer ``self.<name>`` — methods, class
    # attributes and anything assigned to ``self`` in a method body.
    # Deliberately over-collected: a name here silences the rule.
    attributes: frozenset[str]
    # False when the class does something that makes its attributes
    # unknowable (``setattr``, a ``__getattr__``), so no handler can be
    # called missing.
    attributes_known: bool
    # False when the class replaces ``on`` with an event source this rule
    # could not resolve, so no event name can be called impossible.
    events_known: bool


def _charm_classes(module: models.Module, custom_events: set[str]) -> Iterator[_CharmClass]:
    """Yield each class in *module* whose ``self.on`` is the charm's own.

    Only a class whose bases are *all* ``ops.CharmBase`` qualifies. A charm
    built on an intermediate base class — a shared base in another package,
    or one of the framework wrappers — inherits handlers this rule cannot
    see and may inherit a different ``on``, so it is skipped rather than
    guessed at.
    """
    imports = _ast.Imports.of(module)
    for node in module.walk(ast.ClassDef):
        bases = _base_names(node, imports)
        if not bases or any(base not in _CHARM_BASES for base in bases):
            continue
        yield _CharmClass(
            node=node,
            attributes=frozenset(_attribute_names(node)),
            attributes_known=not _has_dynamic_attributes(node),
            events_known=_events_are_known(node, custom_events),
        )


def _attribute_names(node: ast.ClassDef) -> Iterator[str]:
    """Yield every name ``self.<name>`` could resolve to on *node*.

    Methods (at any nesting, so one defined under ``if TYPE_CHECKING:``
    still counts), class-level assignments, and attributes assigned to
    ``self`` anywhere in the body.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            yield child.name
        elif (
            isinstance(child, ast.Attribute)
            and isinstance(child.ctx, ast.Store)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
        ):
            yield child.attr
    for statement in node.body:
        # A class-body import binds a class attribute, which is how a
        # charm too big for one file hangs its action handlers off
        # ``from actions.enable import on_enable_action``.
        if isinstance(statement, ast.Import | ast.ImportFrom):
            for alias in statement.names:
                yield (alias.asname or alias.name).split(".", 1)[0]
            continue
        targets = (
            [statement.target]
            if isinstance(statement, ast.AnnAssign)
            else statement.targets
            if isinstance(statement, ast.Assign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name):
                yield target.id


def _has_dynamic_attributes(node: ast.ClassDef) -> bool:
    """Whether *node* can grow attributes this rule cannot enumerate."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "setattr":
            return True
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) and child.name in (
            "__getattr__",
            "__getattribute__",
        ):
            return True
    return False


def _events_are_known(node: ast.ClassDef, custom_events: set[str]) -> bool:
    """Whether *node*'s ``on`` is an event source this rule can enumerate.

    A charm that declares its own ``on = MyCharmEvents()`` is understood
    when ``MyCharmEvents`` is one of the ``CharmEvents`` subclasses found
    in the charm tree. When it is not — a base class from a pip
    dependency, say — the events it adds are invisible, and the rule
    stays silent for the whole class.
    """
    for statement in node.body:
        if not isinstance(statement, ast.AnnAssign | ast.Assign):
            continue
        targets = [statement.target] if isinstance(statement, ast.AnnAssign) else statement.targets
        if not any(isinstance(t, ast.Name) and t.id == "on" for t in targets):
            continue
        value = statement.value
        if not isinstance(value, ast.Call):
            return False
        name = _ast.dotted_name(value.func)
        if name is None or name.rsplit(".", 1)[-1] not in custom_events:
            return False
    return True


class ObserveTargetMismatch(Rule):
    """Detect ``framework.observe()`` calls that cannot possibly work.

    Both arguments are resolved: the event has to be one the charm
    really has, and the handler has to be a method the charm class
    really defines. Either one wrong is an ``AttributeError`` the first
    time the charm is constructed, which is every hook — the charm is
    completely dead, and only a deploy shows it. Rename refactors are
    the usual cause: an endpoint renamed in ``charmcraft.yaml`` but not
    in ``src/``, or a handler renamed and one observer missed.

    Silence is the answer to anything the rule cannot resolve: an event
    reference built from a variable, a handler on another object, a
    charm class with a base this rule cannot see, a custom event source
    it cannot find, or a ``define_event`` call with a computed name. A
    charm that is merely hard to read must not be reported as broken.
    Each half is silenced on its own, so a charm whose event names are
    unknowable is still checked for handlers that do not exist.

    Both halves are reported when both are broken. Only the event
    raises at runtime — the arguments are evaluated left to right — but
    a rename refactor that missed both wants both listed, so that one
    pass over the findings fixes the call rather than two.
    """

    category = "CORRECTNESS"
    number = 8
    name = "observe-target-mismatch"
    description = "framework.observe() names an event or handler that cannot exist"
    default_severity = models.Severity.ERROR
    reference_url = (
        "https://canonical.com/juju/docs/ops/latest/reference/ops/#ops.Framework.observe"
    )
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
            requires:
              database:
                interface: postgresql_client
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.db_relation_changed, self._on_database_changed)

                def _on_database_changed(self, event: ops.RelationChangedEvent):
                    self._replan()
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.database_relation_changed, self._on_database_changed)

                def _on_database_changed(self, event: ops.RelationChangedEvent):
                    self._replan()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        custom_events, complete = _custom_event_names(context)
        known_events = self._known_events(context, custom_events) if complete else None
        diagnostics: list[models.Diagnostic] = []
        for module in context.charm_sources():
            observers = _ast.observers(module)
            for charm in _charm_classes(module, custom_events):
                diagnostics.extend(self._check_class(charm, observers, module, known_events))
        return diagnostics

    def _known_events(
        self, context: models.CharmContext, custom_events: set[str]
    ) -> set[str] | None:
        """Return every event the charm can have, or ``None`` if unknowable.

        A charm with no metadata at all has nothing to derive event names
        from, and reporting every metadata-derived event as impossible
        would be a rule failure rather than a charm one.
        """
        if not context.metadata.present:
            return None
        known = set(_LIFECYCLE_EVENTS) | custom_events
        sections = {
            "relations": _names(context.metadata.get("provides"))
            | _names(context.metadata.get("requires"))
            | _names(context.metadata.get("peers")),
            "storage": _names(context.metadata.get("storage")),
            "containers": _names(context.metadata.get("containers")),
            "actions": _names(context.actions),
        }
        for suffix, section, _ in _METADATA_EVENTS:
            known.update(f"{name}{suffix}" for name in sections[section])
        return known

    def _check_class(
        self,
        charm: _CharmClass,
        observers: list[_ast.Observer],
        module: models.Module,
        known_events: set[str] | None,
    ) -> Iterator[models.Diagnostic]:
        """Report each broken ``observe`` call in one charm class."""
        nodes = {id(node) for node in ast.walk(charm.node)}
        for observer in observers:
            if id(observer.call) not in nodes:
                continue
            for diagnostic in (
                self._check_event(observer, charm, module, known_events),
                self._check_handler(observer, charm, module),
            ):
                if diagnostic is not None:
                    yield diagnostic

    def _check_event(
        self,
        observer: _ast.Observer,
        charm: _CharmClass,
        module: models.Module,
        known_events: set[str] | None,
    ) -> models.Diagnostic | None:
        """Report an event the charm cannot have, if this is one."""
        if known_events is None or not charm.events_known or observer.event is None:
            return None
        # Only the charm's own ``self.on`` is described by the charm's
        # metadata; ``self.<lib>.on.<event>`` belongs to that library.
        if _on_receiver(observer.call.args[0]) != "self":
            return None
        if observer.event in known_events:
            return None
        return self.diagnostic(
            f"Charm has no event 'self.on.{observer.event}' — it is not a lifecycle event, "
            f"and nothing declared in the charm's metadata defines it",
            path=module.path,
            line=observer.call.args[0].lineno,
            fix_hint=self._event_hint(observer.event),
        )

    def _event_hint(self, event: str) -> str:
        """Suggest the declaration a metadata-derived event name is missing."""
        for suffix, _, declaration in _METADATA_EVENTS:
            if event.endswith(suffix) and len(event) > len(suffix):
                name = event[: -len(suffix)].replace("_", "-")
                return (
                    f"Declare '{name}' as {declaration} in charmcraft.yaml, "
                    f"or correct the event name"
                )
        return "Correct the event name, or define it on the charm's `CharmEvents` subclass"

    def _check_handler(
        self, observer: _ast.Observer, charm: _CharmClass, module: models.Module
    ) -> models.Diagnostic | None:
        """Report a handler the charm class does not define, if this is one."""
        if not charm.attributes_known or observer.handler is None:
            return None
        if observer.handler in charm.attributes:
            return None
        return self.diagnostic(
            f"Observer handler 'self.{observer.handler}' is not defined on '{charm.node.name}'",
            path=module.path,
            line=observer.call.args[1].lineno,
            fix_hint=(
                f"Define `{observer.handler}` on '{charm.node.name}', "
                f"or point the observer at the handler it was renamed to"
            ),
        )


class ContainerNameMismatch(Rule):
    """Detect ``get_container()`` calls naming an undeclared container.

    A container name that isn't declared under ``containers:`` raises
    ``ops.ModelError`` the first time the hook runs, and the classic way
    to get there is to assume the container is named after the app.

    Only the charm's own ``src/`` is checked. A library the charm
    publishes is written to run inside *other* charms, so a container
    name there refers to a container this charm's metadata has no reason
    to declare.

    Nothing is reported unless the charm declares at least one container
    of its own, and nothing at all is reported for a charm using a
    charmcraft ``extensions:`` profile. Both are cases where the
    containers charmcraft ends up building are not the containers
    charmlint can read: a ``go-framework`` charm's ``app`` container is
    injected by the extension, and a charm whose metadata is generated
    (from a ``metadata.yaml.j2``, say) declares its containers somewhere
    charmlint never sees. Reporting those means reporting a charm we
    failed to understand.
    """

    category = "CORRECTNESS"
    number = 9
    name = "container-name-mismatch"
    description = "get_container() names a container not declared in containers:"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-containers"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
            containers:
              nginx:
                resource: nginx-image
            resources:
              nginx-image:
                type: oci-image
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _replan(self):
                    container = self.unit.get_container("web-frontend")
                    container.replan()
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _replan(self):
                    container = self.unit.get_container("nginx")
                    container.replan()
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if context.metadata.get("extensions"):
            return []
        containers = context.metadata.get("containers")
        declared = {str(name) for name in containers}
        if not declared:
            return []
        diagnostics: list[models.Diagnostic] = []
        for module in context.modules(models.Scope.SRC):
            for name in _get_container_names(module):
                if name.value in declared:
                    continue
                known = ", ".join(f"'{c}'" for c in sorted(declared))
                diagnostics.append(
                    self.diagnostic(
                        f"get_container('{name.value}') does not match a container "
                        f"declared in {containers.source} — declared: {known}",
                        path=module.path,
                        line=name.lineno,
                        fix_hint=(
                            f"Use one of the declared names, or add '{name.value}' "
                            f"to 'containers:'"
                        ),
                    )
                )
        return diagnostics


_GET_CONTAINER = "get_container"
_NAME_KEYWORD = "container_name"


def _get_container_names(module: models.Module) -> list[ast.Constant]:
    """Return the name node of each ``get_container("name")`` call in *module*.

    Matched on the method name alone. ``get_container`` is
    ``ops.Unit.get_container`` in practice — charmlint has no type
    inference, so a same-named method on an unrelated object would match
    too, but no such method is in common use in charms.
    """
    found: list[ast.Constant] = []
    for call in module.walk(ast.Call):
        if not isinstance(call.func, ast.Attribute) or call.func.attr != _GET_CONTAINER:
            continue
        name = _container_name(call)
        if name is not None:
            found.append(name)
    return found


def _container_name(call: ast.Call) -> ast.Constant | None:
    """Return the string-literal name a ``get_container`` call asks for.

    ``None`` for a name this rule cannot read: a variable, an f-string, a
    lookup into ``self.meta.containers``. Those are the spellings that
    *cannot* be checked against the declared names, and they are also the
    spellings that are usually right, so leaving them alone costs little.
    """
    argument = call.args[0] if call.args else _ast.keyword(call, _NAME_KEYWORD)
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument
    return None
