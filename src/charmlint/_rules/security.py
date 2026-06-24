"""Security rules — secrets management, TLS support."""

import ast
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


def _is_url_fetch_call(call: ast.Call) -> bool:
    """True if ``call`` looks like a URL fetch: urllib.request.urlopen,
    requests.get, or subprocess.run([...wget|curl...])."""
    func = call.func
    # urllib.request.urlopen(...)
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "urlopen"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "request"
    ):
        return True
    # requests.get(...)
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id == "requests"
    ):
        return True
    # subprocess.run([...]) with first elt starting with "wget" or "curl"
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "run"
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
        and call.args
        and isinstance(call.args[0], (ast.List, ast.Tuple))
        and call.args[0].elts
        and isinstance(call.args[0].elts[0], ast.Constant)
        and isinstance(call.args[0].elts[0].value, str)
    ):
        first = call.args[0].elts[0].value
        if (
            first == "wget"
            or first == "curl"
            or first.endswith("/wget")
            or first.endswith("/curl")
        ):
            return True
    return False


def _function_uses_integrity_check(func: ast.FunctionDef) -> bool:
    """True if the function body references hashlib or sha256sum."""
    for node in ast.walk(func):
        # hashlib.<anything> attribute access or `import hashlib` usage.
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "hashlib"
        ):
            return True
        # subprocess invocation of `sha256sum` or any literal mentioning it.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "sha256sum" in node.value
        ):
            return True
    return False


class DownloadWithoutChecksum(Rule):
    """Flag machine-charm URL fetches with no integrity check in the same function."""

    id = "SEC006"
    name = "download-without-checksum"
    description = "Machine charm downloads software via URL fetch without a checksum verification"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Only applies to machine charms — skip if `containers:` is declared.
        containers = context.metadata.get("containers")
        if isinstance(containers, dict) and containers:
            return []

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
                fetches = [
                    n for n in ast.walk(node) if isinstance(n, ast.Call) and _is_url_fetch_call(n)
                ]
                if not fetches:
                    continue
                if _function_uses_integrity_check(node):
                    continue
                for call in fetches:
                    diagnostics.append(
                        self.diagnostic(
                            f"Function '{node.name}' fetches a URL but does not "
                            f"verify the downloaded content with a checksum "
                            f"(no hashlib or sha256sum in the same function)",
                            path=str(path),
                            line=call.lineno,
                            fix_hint=(
                                "After downloading, compute a sha256 with hashlib "
                                "(or run sha256sum) and compare against a known-good digest"
                            ),
                        )
                    )
        return diagnostics
