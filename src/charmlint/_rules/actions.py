"""Action rules — declared actions vs. observers wired up in src/."""

from .. import _ast
from .. import _models as models
from ._base import Rule


class ActionMissingObserver(Rule):
    """Every declared action must have a ``framework.observe`` registration.

    Only observe calls in the charm's own ``src/`` are considered.
    Charms whose observe calls live in an external base class (installed
    as a pip dependency, not vendored under ``src/`` or ``lib/``) will
    hit false positives — disable ACTIONS-001 in that case.
    """

    category = "ACTIONS"
    number = 1
    name = "action-missing-observer"
    description = "Action declared in charmcraft.yaml has no observer in src/"
    default_severity = models.Severity.WARNING
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            actions:
              rotate-logs:
                description: Rotate the workload's log files.
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.config_changed, self._on_config_changed)

                def _on_config_changed(self, event: ops.ConfigChangedEvent):
                    ...
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.config_changed, self._on_config_changed)
                    framework.observe(self.on.rotate_logs_action, self._on_rotate_logs)

                def _on_config_changed(self, event: ops.ConfigChangedEvent):
                    ...

                def _on_rotate_logs(self, event: ops.ActionEvent):
                    ...
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if not context.actions:
            return []
        observed = {
            observer.action
            for module in context.charm_sources()
            for observer in _ast.observers(module)
            if observer.action is not None
        }
        diagnostics: list[models.Diagnostic] = []
        for action_name in context.actions:
            if action_name in observed:
                continue
            handler = "_on_" + action_name.replace("-", "_")
            diagnostics.append(
                self.diagnostic(
                    f"Action '{action_name}' has no observer "
                    f"(expected `framework.observe(self.on['{action_name}'].action, ...)`)",
                    fix_hint=(
                        f"Add `framework.observe(self.on['{action_name}'].action, "
                        f"self.{handler})` in __init__ and a matching handler"
                    ),
                )
            )
        return diagnostics


class ActionMissingAdditionalProperties(Rule):
    """Every declared action should state ``additionalProperties`` explicitly.

    Juju 4 flipped the default relative to Juju 3, so an action that
    omits the field accepts unknown parameters on one version and
    rejects them on the other. Either value silences the rule — the
    point is that the charm has made the choice, not that it made a
    particular one.

    Actions declared without a body (``do-thing:`` with no mapping) are
    flagged too: they have no ``additionalProperties`` either.
    """

    category = "ACTIONS"
    number = 2
    name = "action-missing-additional-properties"
    description = "Action does not explicitly set 'additionalProperties'"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-actions"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            actions:
              rotate-logs:
                description: Rotate the workload's log files.
                params:
                  keep:
                    type: integer
                    description: How many rotated files to keep.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            actions:
              rotate-logs:
                description: Rotate the workload's log files.
                params:
                  keep:
                    type: integer
                    description: How many rotated files to keep.
                additionalProperties: false
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for action_name, body in context.actions.items():
            if "additionalProperties" in body:
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Action '{action_name}' does not set 'additionalProperties' — "
                    f"Juju 3 and Juju 4 default it differently",
                    fix_hint=(
                        f"Add `additionalProperties: false` to '{action_name}' "
                        f"(or `true` if unknown parameters are intended)"
                    ),
                )
            )
        return diagnostics


def _action_params(action: models.Yaml) -> models.Yaml:
    """Return the node holding an action's parameter definitions.

    Juju's schema puts parameters directly under ``params`` — that mapping
    *is* the JSON Schema ``properties`` object. Some charms nest an explicit
    ``properties`` key inside ``params`` instead, so unwrap that when present.
    """
    params = action.get("params")
    properties = params.get("properties")
    if isinstance(properties.value, dict):
        return properties
    return params


class ActionMissingDescription(Rule):
    """Every declared action should document what it does.

    ``juju actions <app>`` lists each action with its description; without
    one, operators have to read the charm source to find out what running
    the action will do.
    """

    category = "ACTIONS"
    number = 3
    name = "action-missing-description"
    description = "Action declared without a description"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-actions"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            actions:
              rotate-logs:
                additionalProperties: false
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            actions:
              rotate-logs:
                description: Rotate the workload's log files.
                additionalProperties: false
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for action_name, action in context.actions.items():
            description = action.get("description").value
            if isinstance(description, str) and description.strip():
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Action '{action_name}' is missing a description",
                    path=action.source,
                    line=action.line,
                    fix_hint=(
                        f"Add a `description:` to the '{action_name}' action explaining "
                        f"what it does and when to run it"
                    ),
                )
            )
        return diagnostics


class ActionParamMissingDescription(Rule):
    """Every action parameter should document what it controls.

    Parameter descriptions are surfaced by ``juju actions --schema``, so a
    parameter without one leaves operators guessing at accepted values.
    """

    category = "ACTIONS"
    number = 4
    name = "action-param-missing-description"
    description = "Action parameter declared without a description"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-actions"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            actions:
              rotate-logs:
                description: Rotate the workload's log files.
                params:
                  keep:
                    type: integer
                additionalProperties: false
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            actions:
              rotate-logs:
                description: Rotate the workload's log files.
                params:
                  keep:
                    type: integer
                    description: How many rotated files to keep.
                additionalProperties: false
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for action_name, action in context.actions.items():
            for param_name, param in _action_params(action).items():
                # A parameter written as a bare scalar (``verbose: boolean``)
                # is a shorthand Juju does not accept; leave it to whichever
                # rule validates the parameter schema itself.
                if not isinstance(param.value, dict):
                    continue
                description = param.get("description").value
                if isinstance(description, str) and description.strip():
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"Action '{action_name}' parameter '{param_name}' "
                        f"is missing a description",
                        path=param.source,
                        line=param.line,
                        fix_hint=(
                            f"Add a `description:` to the '{param_name}' parameter of the "
                            f"'{action_name}' action"
                        ),
                    )
                )
        return diagnostics
