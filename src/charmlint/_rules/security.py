"""Security rules — secrets management, TLS support."""

import re

from .. import _models as models
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
        # Recognise both legacy spellings and the ops secrets API:
        # self.app.add_secret(), self.model.get_secret(), Secret.get_content(),
        # SecretChanged / SecretRotate events, ops.Secret, secret.grant(...).
        has_juju_secrets = bool(
            re.search(
                r"juju.*secret"
                r"|\b(?:add_secret|get_secret)\b"
                r"|\bSecret(?:Changed|Rotate|Remove|Expired)\b"
                r"|\bops\.Secret\b",
                all_source,
            )
        )

        # Look for config options with secret-looking names — but skip any
        # option that's already declared `type: secret`, since its value is
        # a secret URI rather than plain text.
        secret_opts: list[str] = []
        for opt_name, opt_spec in context.config_options.items():
            if isinstance(opt_spec, dict) and opt_spec.get("type") == "secret":
                continue
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


class HardcodedSecretDefault(Rule):
    """Flag secret-type or secret-named config options that ship a non-empty default."""

    id = "SEC008"
    name = "hardcoded-secret-default"
    description = "Secret-type or secret-named config option has a non-empty default value"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for opt_name, opt_spec in context.config_options.items():
            if not isinstance(opt_spec, dict):
                continue
            is_secret_type = opt_spec.get("type") == "secret"
            is_secret_name = any(kw in opt_name.lower() for kw in _SECRET_CONFIG_KEYWORDS)
            if not (is_secret_type or is_secret_name):
                continue
            if "default" not in opt_spec:
                continue
            default = opt_spec["default"]
            if default is None or default == "":
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Config option '{opt_name}' is a secret but ships a "
                    f"hardcoded default value — secrets must not be baked into the charm",
                    path="charmcraft.yaml",
                    fix_hint=(
                        "Remove the default and require operators to supply the secret "
                        "via `juju config` or a Juju secret"
                    ),
                )
            )
        return diagnostics
