"""Security rules — secrets management, TLS support."""

import ast
import re

from .. import _models as models
from . import Rule

_SECRET_CONFIG_KEYWORDS = {"password", "secret", "token", "api-key", "api_key", "credential"}

# Variable-name pattern used by SEC004 to flag sensitive values interpolated
# into logger calls.  Matches the *name* of the bound variable, not its value.
_SENSITIVE_NAME_RE = re.compile(
    r"password|secret|token|api[-_]?key|credential|private[-_]?key",
    re.IGNORECASE,
)
_LOG_LEVELS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical"})


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


class SensitiveValueInLogs(Rule):
    """Flag logger calls that interpolate variables with sensitive-looking names.

    The check is name-based (speculative) — it inspects the *name* of the bound
    variable interpolated into the f-string, not its runtime value.  This keeps
    false positives bounded: an f-string like ``f"got {password}"`` is flagged,
    while ``f"got {something}"`` (no sensitive keyword in the name) is not.
    Plain string literals such as ``logger.info("plain password")`` are ignored
    because no variable is being interpolated.  Charm libraries under ``lib/``
    are skipped — they aren't this charm's code to fix.
    """

    id = "SEC004"
    name = "sensitive-value-in-logs"
    description = "Logger call interpolates a variable whose name suggests a secret"
    default_severity = models.Severity.ERROR

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr in _LOG_LEVELS
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "logger"
                ):
                    continue
                if not node.args:
                    continue
                first = node.args[0]
                if not isinstance(first, ast.JoinedStr):
                    continue
                for piece in first.values:
                    if not isinstance(piece, ast.FormattedValue):
                        continue
                    inner = piece.value
                    if not isinstance(inner, ast.Name):
                        continue
                    if _SENSITIVE_NAME_RE.search(inner.id):
                        diagnostics.append(
                            self.diagnostic(
                                f"Logger call interpolates variable '{inner.id}' "
                                f"whose name suggests a secret — value may be "
                                f"written to logs",
                                path=str(path),
                                line=node.lineno,
                                fix_hint=(
                                    "Avoid logging secret values; log a redacted "
                                    "placeholder or omit the field entirely"
                                ),
                            )
                        )
        return diagnostics
