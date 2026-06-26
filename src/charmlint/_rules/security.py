"""Security rules — secrets management, TLS support.

SEC001 lives here; SEC002 returns in its own PR.
"""

import re

from .. import _models as models
from . import Rule

# Match a secret-like keyword only when it appears as the terminal
# hyphen/underscore-separated component of the config name.
_SECRET_KEYWORD_RE = re.compile(
    r"(?:^|[-_])(?:password|secret|token|api[-_]key|credential)$",
    re.IGNORECASE,
)


class SecretInPlainConfig(Rule):
    """Detect config options that look like secrets but aren't using Juju secrets."""

    id = "SEC001"
    name = "secret-in-plain-config"
    description = "Secret-like config option found — use Juju secrets instead"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        all_source = "\n".join(
            content for path, content in context.python_sources.items() if "lib" not in path.parts
        )
        has_juju_secrets = bool(
            re.search(
                r"juju.*secret"
                r"|\b(?:add_secret|get_secret)\b"
                r"|\bSecret(?:Changed|Rotate|Remove|Expired)\b"
                r"|\bops\.Secret\b",
                all_source,
            )
        )

        secret_opts: list[str] = []
        for opt_name, opt_spec in context.config_options.items():
            if isinstance(opt_spec, dict) and opt_spec.get("type") == "secret":
                continue
            if _SECRET_KEYWORD_RE.search(opt_name):
                secret_opts.append(opt_name)

        if secret_opts and not has_juju_secrets:
            diagnostics: list[models.Diagnostic] = []
            for opt in secret_opts:
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt}' looks like a secret "
                        f"— use Juju secrets instead of plain-text config",
                        path="charmcraft.yaml",
                        fix_hint="Use the Juju secrets API for sensitive data",
                    )
                )
            return diagnostics
        return []
