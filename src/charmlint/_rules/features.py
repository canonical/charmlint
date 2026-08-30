"""Feature rules — charm behaviour a charm is expected to implement."""

import ast

from .. import _ast
from .. import _models as models
from ._base import Rule

# The names a charm's own base class resolves to, whichever spelling the
# source used: ``ops.CharmBase``, ``from ops import CharmBase``, or the
# older ``from ops.charm import CharmBase``.
_CHARM_BASES = frozenset({"ops.CharmBase", "ops.charm.CharmBase"})

# Every spelling of the event that a charm's source might carry: the ops
# event attribute, the ops event class, and the hook name as a string.
_UPGRADE_NAMES = frozenset({"upgrade_charm", "upgrade-charm", "UpgradeCharmEvent"})
# Helpers that wire events for the charm rather than at the call site:
# ``cosl.reconciler``'s ``observe_events(self, all_events, self._reconcile)``
# and its kin, and the reconciler objects of ``charms.reconciler`` and
# ``charmed_kubeflow_chisme``, which walk ``charm.on.events()`` and observe
# the lot. Either way the registered events are named inside the helper.
_OBSERVE_PREFIX = "observe"
_RECONCILER_SUFFIX = "Reconciler"


def _defines_charm_class(module: models.Module) -> bool:
    """Whether *module* defines an ``ops.CharmBase`` subclass.

    A visible subclass is what makes the rest of the rule sound: the class
    the framework will instantiate is there to be read. A charm whose class
    derives from a base installed as a pip dependency — ``paas_charm``,
    ``ops_openstack``, ``ops_sunbeam`` — is left alone, because the observe
    calls that base makes are not in the tree, and "this charm ignores
    upgrades" would be a guess about code charmlint cannot see. That is
    also why an ``ops.main(...)`` call is not taken as evidence on its own:
    a ``main`` call whose class charmlint cannot read is exactly the case
    being excluded.
    """
    imports = _ast.Imports.of(module)
    return any(
        imports.resolve(base) in _CHARM_BASES
        for node in module.walk(ast.ClassDef)
        for base in node.bases
    )


def _names_upgrade(module: models.Module) -> bool:
    """Whether *module* names the upgrade-charm event, in any position.

    The obvious form is ``framework.observe(self.on.upgrade_charm, ...)``,
    but the corpus handles the upgrade in three more shapes that no observe
    call of the charm's own would catch: handing ``self.on.upgrade_charm``
    to a library that observes it on the charm's behalf (a
    ``refresh_events`` list), passing ``ops.UpgradeCharmEvent`` to a helper
    that does the observing, and branching on the hook name in ``__init__``
    rather than observing anything. Naming the event at all therefore
    counts as handling it — a charm that has thought about upgrades has
    nothing to learn here, and the rule is about the ones that never
    mention them.
    """
    for node in module.walk(ast.Attribute, ast.Name, ast.Constant):
        if isinstance(node, ast.Attribute):
            if node.attr in _UPGRADE_NAMES:
                return True
        elif isinstance(node, ast.Name):
            if node.id in _UPGRADE_NAMES:
                return True
        elif isinstance(node.value, str) and node.value in _UPGRADE_NAMES:
            return True
    return False


def _wiring_is_readable(module: models.Module) -> bool:
    """Whether every event *module* registers can be read at the call site.

    False for an observe call whose event expression could not be decoded,
    and for a call to an ``observe_*`` helper or a ``*Reconciler``, which
    register a set of events named inside themselves rather than here.
    Telling a charm it never handles upgrades on the strength of wiring the
    rule failed to read is the false positive most worth designing against,
    so any of those shapes silences the rule.
    """
    if any(not observer.resolved for observer in _ast.observers(module)):
        return False
    for call in module.walk(ast.Call):
        name = _ast.dotted_name(call.func)
        trailing = name.rpartition(".")[2] if name else ""
        if trailing.startswith(_OBSERVE_PREFIX) and trailing != _OBSERVE_PREFIX:
            return False
        if trailing.endswith(_RECONCILER_SUFFIX):
            return False
    return True


class NoUpgradeCharmObserver(Rule):
    """Detect a charm that never mentions the ``upgrade-charm`` event.

    Reported only when the charm's wiring is legible end to end: its class
    subclasses ``ops.CharmBase`` here, it registers its events with
    ``framework.observe`` here, and every one of those registrations names
    an event this rule could read. Anything less and the missing event may
    simply be somewhere charmlint cannot look.

    Only the charm's own code counts, in both directions: a vendored
    ``lib/charms/<someone else>/`` copy neither makes a repository a charm
    nor answers for the charm's own upgrade. A charm that pulls in a
    library observing ``upgrade-charm`` gets that library's concern
    refreshed — its dashboards re-pushed, its scrape jobs re-sent — which
    says nothing about the charm's own workload.

    Informational: plenty of charms genuinely have nothing to do on an
    upgrade, and Juju fires ``config-changed`` afterwards, so a holistic
    charm may already reconcile. The finding is worth a look rather than a
    fix — a charm that installs a snap, writes a systemd unit, or keeps
    on-disk state, and never redoes any of it on upgrade, is the case this
    is fishing for.
    """

    category = "FEATURES"
    number = 1
    name = "no-upgrade-charm-observer"
    description = "Charm does not observe the upgrade-charm event"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/juju/stable/reference/hook/#upgrade-charm"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        is_charm = False
        observes_anything = False
        for module in context.charm_sources():
            if _names_upgrade(module) or not _wiring_is_readable(module):
                return []
            is_charm = is_charm or _defines_charm_class(module)
            observes_anything = observes_anything or bool(_ast.observers(module))
        # A charm that registers nothing at all is wiring its events some
        # way this rule cannot enumerate — a base class, a decorator, a
        # component framework — so the absence of one event means nothing.
        if not is_charm or not observes_anything:
            return []
        return [
            self.diagnostic(
                "Charm does not observe the upgrade-charm event — an upgraded unit "
                "starts from whatever the previous revision left on disk, with no "
                "chance to migrate it, refresh the workload, or update its peers",
                fix_hint=(
                    "Observe the event, e.g. "
                    "`self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)`, "
                    "or have a holistic handler reconcile the unit on it"
                ),
            )
        ]
