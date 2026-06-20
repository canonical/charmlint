"""Security rules — secrets management, TLS support."""

import re

from .. import models
from . import Rule

_SECRET_CONFIG_KEYWORDS = {"password", "secret", "token", "api-key", "api_key", "credential"}


class SecretInPlainConfig(Rule):
    """Detect config options that look like secrets but aren't using Juju secrets."""

    id = "SEC001"
    name = "secret-in-plain-config"
    description = "Secret-like config option found — use Juju secrets instead"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Check if the charm uses Juju secrets API.
        all_source = "\n".join(
            content for path, content in context.python_sources.items() if "lib" not in path.parts
        )
        has_juju_secrets = bool(re.search(r"juju.*secret|Secret(?:Changed|Rotate)", all_source))

        # Look for config options with secret-looking names.
        secret_opts: list[str] = []
        for opt_name in context.config_options:
            if any(kw in opt_name.lower() for kw in _SECRET_CONFIG_KEYWORDS):
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


class NoTLSSupport(Rule):
    """Check for TLS/encryption support."""

    id = "SEC002"
    name = "no-tls-support"
    description = "No TLS/encryption support detected"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Check for tls-certificates relation.
        for section in ("requires", "provides", "peers"):
            for rel_def in context.metadata.get(section, {}).values():
                if isinstance(rel_def, dict) and rel_def.get("interface") in (
                    "tls-certificates",
                    "certificates",
                ):
                    return []

        # Check source for TLS-related code.
        all_source = "\n".join(context.python_sources.values())
        if re.search(r"\btls\b|\bcertificate\b|\bssl\b", all_source, re.IGNORECASE):
            return []

        return [
            self.diagnostic(
                "No TLS/encryption support detected",
                fix_hint="Add a tls-certificates relation for encryption in transit",
            )
        ]
