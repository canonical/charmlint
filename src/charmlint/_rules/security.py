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
# flag, not a credential. 'type: secret' is a Juju secret already.
_NON_SECRET_TYPES = frozenset({"boolean", "int", "float", "secret"})


class SecretInPlainConfig(Rule):
    """Detect config options that look like secrets but aren't using Juju secrets."""

    category = "SECURITY"
    number = 1
    name = "secret-in-plain-config"
    description = "Secret-like config option found — use Juju secrets instead"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/ops/latest/howto/manage-secrets/"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                database-password:
                  type: string
                  description: Password for the database user.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                database-credentials:
                  type: secret
                  description: >-
                    Juju secret holding the database username and password,
                    granted to this application.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"Config option '{name}' looks like a secret "
                f"— use Juju secrets instead of plain-text config",
                path=option.source,
                line=option.line,
                fix_hint="Use the Juju secrets API for sensitive data",
            )
            for name, option in context.config_options.items()
            if option.get("type").value not in _NON_SECRET_TYPES
            and isinstance(name, str)
            and _SECRET_KEYWORD_RE.search(name)
        ]
