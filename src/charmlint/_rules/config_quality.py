"""Config quality rules — types, defaults, descriptions."""

import ast
from collections.abc import Iterator
from typing import Any

from .. import _ast, _yaml
from .. import _models as models
from ._base import Rule

_CONFIG_REFERENCE_URL = "https://canonical.com/juju/docs/ops/latest/howto/manage-configuration/"

# A 'secret' option holds a user-supplied secret URI, so there is no
# meaningful default a charm author could provide.
_NO_SENSIBLE_DEFAULT_TYPES = frozenset({"secret"})


class ConfigMissingType(Rule):
    """Config options should declare an explicit type."""

    category = "CONFIG"
    number = 1
    name = "config-missing-type"
    description = "Config option is missing a type"
    default_severity = models.Severity.WARNING
    reference_url = _CONFIG_REFERENCE_URL
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  default: 8080
                  description: Port the web server listens on.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: 8080
                  description: Port the web server listens on.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"Config option '{name}' is missing a type",
                path=option.source,
                line=option.line,
                fix_hint="Add an explicit 'type' (string, int, float, boolean, or secret)",
            )
            for name, option in context.config_options.items()
            if not option.get("type")
        ]


class ConfigMissingDefault(Rule):
    """Config options should provide a default value where one makes sense."""

    category = "CONFIG"
    number = 2
    name = "config-missing-default"
    description = "Config option is missing a default value"
    default_severity = models.Severity.INFO
    reference_url = _CONFIG_REFERENCE_URL
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  description: Port the web server listens on.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: 8080
                  description: Port the web server listens on.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"Config option '{name}' is missing a default value",
                path=option.source,
                line=option.line,
                fix_hint="Add a 'default', or leave it out deliberately if the option is required",
            )
            for name, option in context.config_options.items()
            if isinstance(option.value, dict)
            and "default" not in option
            and _yaml.option_type(option) not in _NO_SENSIBLE_DEFAULT_TYPES
        ]


class ConfigMissingDescription(Rule):
    """Config options should be documented with a description."""

    category = "CONFIG"
    number = 3
    name = "config-missing-description"
    description = "Config option is missing a description"
    default_severity = models.Severity.WARNING
    reference_url = _CONFIG_REFERENCE_URL
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: 8080
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: 8080
                  description: Port the web server listens on.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return [
            self.diagnostic(
                f"Config option '{name}' is missing a description",
                path=option.source,
                line=option.line,
                fix_hint="Add a 'description' explaining what the option does",
            )
            for name, option in context.config_options.items()
            if not str(option.get("description").value or "").strip()
        ]


# Spellings that reach the charm's own config mapping from anywhere in the
# charm — the receiver names either a charm or the model, neither of which a
# helper class is likely to own. ``self.config`` is deliberately absent: a
# helper class with its own ``self.config`` dict is common, so that spelling
# is only read inside a charm class (see ``_charm_config_reads``).
_MODEL_CONFIG_SPELLINGS = frozenset({
    "self.model.config",
    "self.charm.config",
    "self.charm.model.config",
    "charm.config",
    "charm.model.config",
})
_SELF_CONFIG = "self.config"
# A class is taken to be a charm if a base resolves to ops' CharmBase, or is
# simply *named* like a charm — charms routinely subclass an intermediate base
# class of their own, and missing those would blind the rule to most charms.
_CHARM_BASE_SUFFIXES = ("Charm", "CharmBase")


def _is_charm_class(node: ast.ClassDef, imports: _ast.Imports) -> bool:
    """Whether *node* looks like a charm class rather than a helper."""
    for base in node.bases:
        resolved = imports.resolve(base)
        if resolved is None:
            continue
        if resolved in _ast.CHARM_BASES or resolved.rsplit(".", 1)[-1].endswith(
            _CHARM_BASE_SUFFIXES
        ):
            return True
    return False


def _keys_read_from(node: ast.AST, spellings: frozenset[str] | set[str]) -> Iterator[ast.expr]:
    """Yield the string-literal key nodes read from a config mapping under *node*.

    Both access forms are matched: ``<config>["x"]`` raises ``KeyError`` when
    ``x`` is undeclared, and ``<config>.get("x")`` quietly returns ``None``.
    A computed key resolves to nothing and is skipped — guessing at its value
    would be worse than missing it.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Subscript):
            target, key = child.value, child.slice
        elif (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "get"
            and child.args
        ):
            target, key = child.func.value, child.args[0]
        else:
            continue
        if _ast.dotted_name(target) in spellings and _ast.dict_key(key) is not None:
            yield key


def _charm_config_reads(module: models.Module) -> Iterator[ast.expr]:
    """Yield every string-literal config key read in *module*."""
    imports = _ast.Imports.of(module)
    yield from _keys_read_from(module.tree, _MODEL_CONFIG_SPELLINGS)
    # Check for `self.config` only in charm classes.
    for node in module.walk(ast.ClassDef):
        if _is_charm_class(node, imports):
            yield from _keys_read_from(node, {_SELF_CONFIG})


class ConfigOptionUndeclared(Rule):
    """Config keys read in ``src/`` must be declared as config options.

    The config schema is a contract between the YAML and the charm code,
    and nothing else checks it: ``self.config.get("prot")`` silently returns
    ``None`` and the charm limps along misconfigured, while the subscript
    form raises ``KeyError`` only once that code path runs.

    Only literal keys in the charm's own ``src/`` are considered. A library
    reads the config of whichever charm uses it, so its keys are not this
    charm's to declare, and a computed key cannot be resolved statically.
    """

    category = "CONFIG"
    number = 6
    name = "config-option-undeclared"
    description = "Config key read in src/ is not a declared config option"
    default_severity = models.Severity.ERROR
    reference_url = _CONFIG_REFERENCE_URL
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: 8080
                  description: Port the web server listens on.
        """,
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _listen_port(self) -> int:
                    return int(self.config["prot"])
        """,
    }
    fix = {
        "src/charm.py": """
            import ops


            class WebFrontendCharm(ops.CharmBase):
                def _listen_port(self) -> int:
                    return int(self.config["port"])
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # With no options declared at all, the charm's config is as likely to
        # be undiscovered as undeclared — a charm keeping its metadata
        # somewhere the linter did not look would light up entirely.
        if not context.config_options:
            return []
        declared = {name for name in context.config_options if isinstance(name, str)}
        diagnostics: list[models.Diagnostic] = []
        for module in context.modules(models.Scope.SRC):
            for key in _charm_config_reads(module):
                name = _ast.dict_key(key)
                if name in declared:
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"Config key '{name}' is read here but is not a declared config option",
                        path=module.path,
                        line=key.lineno,
                        fix_hint=(
                            f"Declare '{name}' under `config.options`, or correct the "
                            f"key to match an option the charm declares"
                        ),
                    )
                )
        return diagnostics


class ConfigDefaultTypeMismatch(Rule):
    """A config option's default must match the type it declares.

    Juju hands the charm the default as written, not coerced to the
    declared type. A ``type: int`` option defaulting to ``"8080"``
    gives the charm a string, and arithmetic on it raises a
    ``TypeError`` in the charm's own code, far from the config. YAML
    1.1 makes this commoner than it sounds: an unquoted ``yes``,
    ``no``, ``on`` or ``off`` is a boolean, so a ``type: string``
    option defaulting to ``no`` never sees a string at all.
    """

    category = "CONFIG"
    number = 7
    name = "config-default-type-mismatch"
    description = "Config option's default value contradicts its declared type"
    default_severity = models.Severity.ERROR
    reference_url = _CONFIG_REFERENCE_URL
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: "8080"
                  description: Port the web server listens on.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: 8080
                  description: Port the web server listens on.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for name, option in context.config_options.items():
            declared = _yaml.option_type(option)
            default = option.get("default")
            # An option with no type is CONFIG-001's finding, and an
            # explicit `default: null` declares no value to check.
            if (
                declared is None
                or declared not in _DEFAULT_TYPES
                or not default.present
                or default.value is None
            ):
                continue
            if isinstance(default.value, _DEFAULT_TYPES[declared]) and not _is_stray_bool(
                declared, default.value
            ):
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Config option '{name}' declares type '{declared}' but its default "
                    f"is {_yaml_type_name(default.value)}",
                    path=default.source,
                    line=default.line,
                    fix_hint=(
                        f"Make the default a '{declared}' value, or change the option's type "
                        f"to match the default"
                    ),
                )
            )
        return diagnostics


# The Python types PyYAML constructs for a well-formed default of each
# declared type. An ``int`` is accepted for a ``float`` option because
# it isn't a defect: ``1`` reaches the charm as written and behaves as
# ``1.0``, and Charmcraft and Juju both accept an integer default.
_DEFAULT_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "int": int,
    "float": (int, float),
    "boolean": bool,
    "secret": str,
}
_YAML_TYPE_NAMES = {str: "a string", bool: "a boolean", int: "an integer", float: "a float"}


def _is_stray_bool(declared: str, default: Any) -> bool:
    """Whether *default* is a bool standing in for a number.

    ``bool`` is a subclass of ``int`` in Python, so ``default: true``
    passes an ``isinstance`` check against ``int`` and ``float`` that
    it has no business passing.
    """
    return declared in {"int", "float"} and isinstance(default, bool)


def _yaml_type_name(default: Any) -> str:
    """Name the type *default* was constructed as, for a diagnostic."""
    # bool before int: it is a subclass, so the plain lookup would miss it.
    for python_type, name in _YAML_TYPE_NAMES.items():
        if isinstance(default, python_type):
            return name
    return f"a {type(default).__name__}"


class ConfigOptionsNotNested(Rule):
    """Config options must sit under an ``options`` key.

    Juju reads a charm's config options from ``options``, one level below
    ``config:`` in ``charmcraft.yaml`` (or at the top level of
    ``config.yaml``). With that level missing, charmcraft still packs the
    charm, and it is ``juju deploy`` that refuses it, with ``invalid config:
    empty configuration``.

    The other config rules still check options written one level too high,
    so their findings are about the options themselves rather than about
    where they are.
    """

    category = "CONFIG"
    number = 8
    name = "config-options-not-nested"
    description = "Config options are not under an `options` key"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-config"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              port:
                type: int
                default: 8080
                description: Port the web server listens on.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                port:
                  type: int
                  default: 8080
                  description: Port the web server listens on.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        section = context.config_section
        if not section or "options" in section:
            return []
        if section.source == "config.yaml":
            where, fix_hint = "config.yaml", "Indent the options under a top-level `options:` key"
        else:
            where, fix_hint = "`config`", "Indent the options under `config.options`"
        # config.yaml's options start at the top of the file, where there is
        # no key line to anchor to, so anchor to the first of them instead.
        line = section.line or next(option.line for _, option in section.items())
        return [
            self.diagnostic(
                f"Config options in {where} are not under an `options` key, "
                f"so Juju will refuse to deploy the charm",
                path=section.source,
                line=line,
                fix_hint=fix_hint,
            )
        ]
