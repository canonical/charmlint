"""Security rules — secrets management, TLS support."""

import re
from typing import Any

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


class OCIImageMutableTag(Rule):
    """Flag OCI-image resources whose upstream-source uses a mutable tag, not a SHA digest."""

    id = "SEC003"
    name = "oci-image-mutable-tag"
    description = "OCI image upstream-source uses a mutable tag instead of a SHA digest"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        resources: dict[str, Any] = context.metadata.get("resources", {}) or {}
        if not isinstance(resources, dict):
            return []

        diagnostics: list[models.Diagnostic] = []
        for res_name, res_def in resources.items():
            if not isinstance(res_def, dict):
                continue
            if res_def.get("type") != "oci-image":
                continue
            upstream = res_def.get("upstream-source")
            if not isinstance(upstream, str) or not upstream:
                continue
            if "@sha256:" in upstream:
                continue
            diagnostics.append(
                self.diagnostic(
                    f"OCI image resource '{res_name}' upstream-source '{upstream}' "
                    f"uses a mutable tag — tags can be overwritten in the registry",
                    path="charmcraft.yaml",
                    fix_hint=(
                        "Pin the image by SHA digest "
                        "(e.g. 'ubuntu/loki@sha256:bef622...') instead of a tag"
                    ),
                )
            )
        return diagnostics
