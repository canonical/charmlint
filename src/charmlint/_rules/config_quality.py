"""Config quality rules — types, defaults, descriptions."""

from .. import _models as models
from ._base import Rule

_CONFIG_REFERENCE_URL = "https://canonical.com/juju/docs/ops/latest/howto/manage-configuration/"

# A 'secret' option holds a user-supplied secret URI, so there is no
# meaningful default a charm author could provide.
_NO_SENSIBLE_DEFAULT_TYPES = frozenset({"secret"})


class ConfigMissingType(Rule):
    """Config options should declare an explicit type."""

    category = "CONFIG"
    number = 1
    name = "config-missing-type"
    description = "Config option is missing a type"
    default_severity = models.Severity.WARNING
    reference_url = _CONFIG_REFERENCE_URL

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"Config option '{name}' is missing a type",
                path=option.source,
                line=option.line,
                fix_hint="Add an explicit 'type' (string, int, float, boolean, or secret)",
            )
            for name, option in context.config_options.items()
            if not option.get("type")
        ]


class ConfigMissingDefault(Rule):
    """Config options should provide a default value where one makes sense."""

    category = "CONFIG"
    number = 2
    name = "config-missing-default"
    description = "Config option is missing a default value"
    default_severity = models.Severity.INFO
    reference_url = _CONFIG_REFERENCE_URL

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"Config option '{name}' is missing a default value",
                path=option.source,
                line=option.line,
                fix_hint="Add a 'default', or leave it out deliberately if the option is required",
            )
            for name, option in context.config_options.items()
            if isinstance(option.value, dict)
            and "default" not in option
            and option.get("type").value not in _NO_SENSIBLE_DEFAULT_TYPES
        ]


class ConfigMissingDescription(Rule):
    """Config options should be documented with a description."""

    category = "CONFIG"
    number = 3
    name = "config-missing-description"
    description = "Config option is missing a description"
    default_severity = models.Severity.WARNING
    reference_url = _CONFIG_REFERENCE_URL

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"Config option '{name}' is missing a description",
                path=option.source,
                line=option.line,
                fix_hint="Add a 'description' explaining what the option does",
            )
            for name, option in context.config_options.items()
            if not str(option.get("description").value or "").strip()
        ]
