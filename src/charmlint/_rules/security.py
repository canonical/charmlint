"""Security rules — secrets management, TLS support."""

import re

from .. import _models as models
from ._base import Rule

# Match a secret-like keyword only when it is the terminal
# hyphen/underscore-separated component of the config name, so that
# names like 'token-timeout' are not flagged.
_SECRET_KEYWORD_RE = re.compile(
    r"(?:^|[-_])(?:password|secret|token|api[-_]key|credential)$",
    re.IGNORECASE,
)

# A secret is always a string; 'inject-password: boolean' is a feature
# flag, not a credential.
_NON_SECRET_TYPES = frozenset({"boolean", "int", "float", "secret"})

# Any of these in the charm source is taken as evidence that the charm
# already knows about Juju secrets.
_JUJU_SECRETS_RE = re.compile(
    r"juju.*secret"
    r"|\b(?:add_secret|get_secret)\b"
    r"|\bSecret(?:Changed|Rotate|Remove|Expired)\b"
    r"|\bops\.Secret\b",
)


class SecretInPlainConfig(Rule):
    """Detect config options that look like secrets but aren't using Juju secrets."""

    category = "SECURITY"
    number = 1
    name = "secret-in-plain-config"
    description = "Secret-like config option found — use Juju secrets instead"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/ops/latest/howto/manage-secrets/"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        secret_options = [
            name
            for name, spec in context.config_options.items()
            if not (isinstance(spec, dict) and spec.get("type") in _NON_SECRET_TYPES)
            and _SECRET_KEYWORD_RE.search(name)
        ]
        if not secret_options:
            return []

        # Charm libraries are vendored, so only the charm's own code counts.
        own_source = "\n".join(
            content for path, content in context.python_sources.items() if "lib" not in path.parts
        )
        if _JUJU_SECRETS_RE.search(own_source):
            return []

        return [
            self.diagnostic(
                f"Config option '{name}' looks like a secret "
                f"— use Juju secrets instead of plain-text config",
                path=context.metadata_source,
                fix_hint="Use the Juju secrets API for sensitive data",
            )
            for name in secret_options
        ]
