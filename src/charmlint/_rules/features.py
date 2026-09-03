"""Feature rules — capabilities a charm declares but never wires up."""

import ast
import dataclasses

from .. import _ast
from .. import _models as models
from ._base import Rule

_CONFIG_CHANGED = "config_changed"

# The ops entry points a charm hands its charm class to. ``ops.main`` is
# both a module and the callable inside it, so both spellings resolve.
_MAIN_TARGETS = frozenset({"ops.main", "ops.main.main"})

# ``ops.CharmBase`` observes nothing on a charm's behalf, so a class
# deriving from it wires up every observer it has. Any other base might,
# which is why the name has to be resolved rather than pattern-matched:
# ``single_kernel_kafka.core.connect_models.ConnectCharmBase`` is spelled
# like an ops base and behaves like a framework.
_OPS_CHARM_BASES = frozenset({"ops.CharmBase", "ops.charm.CharmBase"})


def _mentions_config_changed(module: models.Module) -> bool:
    """Whether *module* names the ``config-changed`` event at all.

    Charms reach the event by more routes than a literal
    ``framework.observe(self.on.config_changed, ...)``: through a local
    alias for ``observe``, through a list of events fed to a holistic
    reconciler, or by handing ``self.on.config_changed`` to a charm
    library as its ``refresh_event``. All of them handle configuration
    changes, and all of them write ``<...>.on.config_changed`` — so the
    event being named anywhere in the charm's own source is taken as the
    charm having dealt with it.
    """
    return any(
        node.attr == _CONFIG_CHANGED
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "on"
        for node in module.walk(ast.Attribute)
    )


def _reads_config(module: models.Module) -> bool:
    """Whether *module* reads the charm's configuration itself.

    ``self.config``, ``self.charm.config``, ``charm.model.config`` — all
    of them are an attribute named ``config``. A charm that declares
    options but never touches them in its own source has handed them to a
    library (``cosl``'s ``Worker`` reads a worker's ``role-*`` options,
    and observes ``config-changed`` to do it), and that library's own
    observers are not visible here.
    """
    return any(node.attr == "config" for node in module.walk(ast.Attribute))


def _callee_name(call: ast.Call) -> str | None:
    """Return the trailing name of whatever *call* calls, else ``None``."""
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _has_opaque_observe(module: models.Module) -> bool:
    """Whether *module* registers observers through something unreadable.

    ``observe_events(self, all_events, self._reconcile)`` — a helper that
    loops over a list of events — registers ``config-changed`` without
    ever naming it. Any observe-shaped call that :func:`_ast.observers`
    could not decode is treated as possibly being one of those.
    """
    decoded = {id(observer.call) for observer in _ast.observers(module)}
    for call in module.walk(ast.Call):
        name = _callee_name(call)
        if name is not None and name.startswith("observe") and id(call) not in decoded:
            return True
    return False


def _main_arguments(module: models.Module, imports: _ast.Imports) -> set[str]:
    """Return the names handed to ``ops.main(...)`` in *module*."""
    names: set[str] = set()
    for call in module.walk(ast.Call):
        if _ast.call_target(call, imports) not in _MAIN_TARGETS or not call.args:
            continue
        name = _ast.dotted_name(call.args[0])
        if name is not None:
            names.add(name)
    return names


def _is_self_attribute(node: ast.expr) -> bool:
    """Whether *node* is ``self.<name>`` — a method or property of the charm."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _reconciles_in_init(node: ast.ClassDef) -> bool:
    """Whether *node*'s ``__init__`` does work rather than only wiring up.

    A statement-level ``self._reconcile()`` in ``__init__`` runs on every
    event the charm is dispatched for, ``config-changed`` included, so the
    charm handles configuration changes without observing anything. This
    is the holistic style the ops documentation now recommends, and it
    leaves no observe call to find.

    Only a bare call *statement* counts. Calls that build the charm's
    collaborators are expressions inside an assignment, and reading a
    property is not a call at all.
    """
    for function in node.body:
        if not isinstance(function, ast.FunctionDef) or function.name != "__init__":
            continue
        for statement in function.body:
            if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                continue
            if _is_self_attribute(statement.value.func):
                return True
    return False


def _delegates_to_collaborator(node: ast.ClassDef) -> bool:
    """Whether *node*'s ``__init__`` hands one of its own methods to a helper.

    ``Reconciler(self, self.reconcile)`` — the ``ops.manifests`` pattern
    the charmed-kubernetes charms are built on — passes the charm and a
    callback to an object that then observes the charm's events itself
    and calls back on each one. The charm is given both, so match on
    both: a call taking a bare ``self`` alongside a ``self.<name>``
    reference is wiring a collaborator up to this charm, and what that
    collaborator observes is not visible here.
    """
    for function in node.body:
        if not isinstance(function, ast.FunctionDef) or function.name != "__init__":
            continue
        for call in ast.walk(function):
            if not isinstance(call, ast.Call):
                continue
            arguments = [*call.args, *(kw.value for kw in call.keywords)]
            passes_self = any(isinstance(a, ast.Name) and a.id == "self" for a in arguments)
            if passes_self and any(_is_self_attribute(a) for a in arguments):
                return True
    return False


@dataclasses.dataclass
class _Classes:
    """What one module's class definitions say about the charm."""

    # Classes deriving straight from ``ops.CharmBase`` — the ones whose
    # observers are all in the charm's own source.
    plain: int = 0
    # A charm class built on a framework base, or on a mixin alongside
    # ``ops.CharmBase``: it inherits observers charmlint cannot see.
    framework: bool = False
    # A charm class that reconciles unconditionally in ``__init__``, or
    # hands a callback to a collaborator that will observe for it.
    holistic: bool = False


def _classes(module: models.Module) -> _Classes:
    """Classify the charm classes *module* defines."""
    imports = _ast.Imports.of(module)
    entry_points = _main_arguments(module, imports)
    result = _Classes()
    for node in module.walk(ast.ClassDef):
        bases = {name for name in (imports.resolve(base) for base in node.bases) if name}
        ops_bases = bases & _OPS_CHARM_BASES
        if ops_bases and not bases - ops_bases:
            result.plain += 1
            result.holistic = (
                result.holistic or _reconciles_in_init(node) or _delegates_to_collaborator(node)
            )
        elif ops_bases or node.name in entry_points:
            # Either a mixin alongside ``ops.CharmBase``, or a charm class
            # whose base is something charmlint cannot see into.
            result.framework = True
    return result


class NoConfigChangedObserver(Rule):
    """Flag a charm that declares config options but never observes ``config-changed``.

    ``config-changed`` is the event Juju emits when an operator runs
    ``juju config``. A charm that declares options and never handles it
    picks the new values up at whatever event happens to fire next, which
    may be much later or never; from the operator's side the setting was
    silently ignored.

    Handling it does not have to mean observing it, and the rule stays
    quiet wherever the charm might be dealing with configuration
    somewhere charmlint cannot see:

    * The charm's own source names ``<...>.on.config_changed`` anywhere —
      observed under an alias, listed for a holistic reconciler, or handed
      to a library as a refresh event.
    * No plain ``ops.CharmBase`` subclass was found in the charm's own
      source: it is either not an ops charm, built on a framework base
      class that observes on its behalf, or assembled somewhere the scan
      does not reach.
    * The charm reconciles unconditionally in ``__init__``, so it runs on
      every event including this one, or hands a callback to a
      collaborator that observes on its behalf.
    * The charm's source wires up no observers at all, which means
      something outside it does.
    * The charm's source never reads its own configuration, so the
      options belong to a library that reads — and observes — them.
    * An observe call could not be read statically — an event held in a
      variable, or a helper that observes a list of events — and it may
      be observing ``config-changed``.
    """

    category = "FEATURES"
    number = 6
    name = "no-config-changed-observer"
    description = "Charm declares config options but does not observe config-changed"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/ops/latest/howto/manage-configuration/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.config_options:
            return []
        charm_classes = 0
        observer_count = 0
        reads_config = False
        for module in context.charm_sources():
            if _mentions_config_changed(module) or _has_opaque_observe(module):
                return []
            classes = _classes(module)
            if classes.framework or classes.holistic:
                return []
            charm_classes += classes.plain
            reads_config = reads_config or _reads_config(module)
            for observer in _ast.observers(module):
                observer_count += 1
                if not observer.resolved or observer.event == _CONFIG_CHANGED:
                    return []
        if not charm_classes or not observer_count or not reads_config:
            return []
        return [
            self.diagnostic(
                "Charm declares config options but never handles 'config-changed' "
                "— operator configuration changes are silently ignored",
                path=context.config_options.source,
                line=context.config_options.line,
                fix_hint=(
                    "Add `framework.observe(self.on.config_changed, self._on_config_changed)` "
                    "in __init__ and a handler that reconciles the workload with the new "
                    "configuration"
                ),
            )
        ]
