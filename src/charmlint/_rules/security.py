"""Security rules — secrets management, TLS support."""

import ast
import re

from .. import _models as models
from . import Rule

_SECRET_CONFIG_KEYWORDS = {"password", "secret", "token", "api-key", "api_key", "credential"}

# Relative-path commands that are conventionally invoked via PATH lookup in
# charm tooling and are safe enough to allow without a fully-qualified path.
_SEC009_ALLOWLIST = frozenset({"python", "python3", "uv", "pip", "pip3", "pytest"})


def _is_subprocess_run(call: ast.Call) -> bool:
    """True if ``call`` is a ``subprocess.run(...)`` invocation."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "run"
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def _has_keyword_true(call: ast.Call, name: str) -> bool:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


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


class SubprocessShellTrue(Rule):
    """Flag ``subprocess.run(..., shell=True)`` calls in charm src/."""

    id = "SEC005"
    name = "subprocess-shell-true"
    description = "subprocess.run() called with shell=True"
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
                if not (isinstance(node, ast.Call) and _is_subprocess_run(node)):
                    continue
                if not _has_keyword_true(node, "shell"):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        "subprocess.run() called with shell=True — interpolated "
                        "values become shell metacharacters and enable command injection",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            "Drop shell=True and pass the command as a list of "
                            "arguments, e.g. subprocess.run(['cmd', 'arg1', 'arg2'])"
                        ),
                    )
                )
        return diagnostics


class SubprocessRelativeBinary(Rule):
    """Flag ``subprocess.run([...])`` calls whose first arg isn't an absolute path."""

    id = "SEC009"
    name = "subprocess-relative-binary"
    description = "subprocess call uses a relative binary path instead of a fully-qualified path"
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
                if not (isinstance(node, ast.Call) and _is_subprocess_run(node)):
                    continue
                if not node.args:
                    continue
                first = node.args[0]
                if not isinstance(first, ast.List) or not first.elts:
                    continue
                head = first.elts[0]
                if not (isinstance(head, ast.Constant) and isinstance(head.value, str)):
                    continue
                cmd = head.value
                if cmd.startswith("/"):
                    continue
                if cmd in _SEC009_ALLOWLIST:
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"subprocess call uses relative binary '{cmd}' — PATH lookups "
                        f"depend on the calling environment and can resolve to "
                        f"unexpected executables",
                        path=str(path),
                        line=node.lineno,
                        fix_hint=(
                            f"Use the fully-qualified path "
                            f"(e.g. '/usr/bin/{cmd}') so the binary is unambiguous"
                        ),
                    )
                )
        return diagnostics
