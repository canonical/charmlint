"""Security rules — secrets management, TLS support."""

import ast
import re

from .. import _models as models
from . import Rule

_SECRET_CONFIG_KEYWORDS = {"password", "secret", "token", "api-key", "api_key", "credential"}
_SENSITIVE_PATH_RE = re.compile(r"conf|config|secret|token|cred|cert", re.IGNORECASE)
_OPEN_WRITE_MODES = frozenset({"w", "w+", "wa"})


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


def _sensitive_literal(node: ast.expr | None) -> str | None:
    """Return the literal string value if it matches the sensitive-path keyword set."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _SENSITIVE_PATH_RE.search(node.value)
    ):
        return node.value
    return None


def _open_write_sensitive_path(call: ast.Call) -> str | None:
    """Return the sensitive path if ``call`` is ``open(<lit>, '<write-mode>')``."""
    if not (isinstance(call.func, ast.Name) and call.func.id == "open"):
        return None
    if len(call.args) < 2:
        return None
    mode_node = call.args[1]
    if not (isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str)):
        return None
    if mode_node.value not in _OPEN_WRITE_MODES:
        return None
    return _sensitive_literal(call.args[0])


def _write_text_sensitive_path(call: ast.Call) -> str | None:
    """Return the sensitive path if ``call`` is ``Path("<lit>").write_text(...)``."""
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "write_text"):
        return None
    receiver = call.func.value
    # Path("/etc/myapp/secrets.conf").write_text(...)
    if (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == "Path"
        and receiver.args
    ):
        return _sensitive_literal(receiver.args[0])
    return None


def _has_chmod_call(func: ast.FunctionDef) -> bool:
    """True if the function body contains a call to ``os.chmod(...)`` or ``<x>.chmod(...)``."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "chmod":
            return True
    return False


class ConfigFileWorldReadable(Rule):
    """Flag functions writing a sensitive-named file without restricting its mode."""

    id = "SEC007"
    name = "config-file-world-readable"
    description = (
        "Sensitive config/credential file opened for writing without "
        "a subsequent chmod to restrict its mode"
    )
    default_severity = models.Severity.WARNING

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
                if not isinstance(node, ast.FunctionDef):
                    continue
                sensitive_path: str | None = None
                for sub in ast.walk(node):
                    if not isinstance(sub, ast.Call):
                        continue
                    sensitive_path = _open_write_sensitive_path(sub) or _write_text_sensitive_path(
                        sub
                    )
                    if sensitive_path:
                        break
                if not sensitive_path:
                    continue
                if _has_chmod_call(node):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"Function '{node.name}' writes sensitive file '{sensitive_path}' "
                        f"without a chmod call — credentials may be left world-readable",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "After writing the file, call `os.chmod(path, 0o600)` "
                            "(or pathlib's `.chmod(0o600)`) to restrict its mode"
                        ),
                    )
                )
        return diagnostics
