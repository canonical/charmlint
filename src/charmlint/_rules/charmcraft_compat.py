"""Charmcraft-compatible rules — checks that mirror ``charmcraft analyse``."""

import ast
import os
import pathlib
import re
from collections.abc import Iterator

from .. import _ast
from .. import _models as models
from ._base import Rule


class DeprecatedSeries(Rule):
    """Flag the deprecated ``series`` key in charm metadata.

    ``series`` named the Ubuntu releases a charm supported, before
    charmcraft moved that onto ``bases`` and then onto ``base`` plus
    ``platforms``. A charm still carrying it is either building for a
    shape charmcraft no longer supports, or carrying a key that no
    longer does anything.

    Presence is the whole test: an empty ``series:`` is flagged like
    any other, because the key itself is the finding rather than what
    it says.
    """

    category = "CHARMCRAFT"
    number = 1
    name = "deprecated-series"
    description = "Deprecated 'series' attribute in metadata"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-platforms"
    example = {
        "metadata.yaml": """
            name: web-frontend
            summary: Serves the web frontend.
            series:
              - jammy
        """,
    }
    fix = {
        "metadata.yaml": """
            name: web-frontend
            summary: Serves the web frontend.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        series = context.metadata.get("series")
        if not series.present:
            return []
        return [
            self.diagnostic(
                "'series' is deprecated in charm metadata — use 'bases' or 'platforms' instead",
                path=series.source,
                line=series.line,
                fix_hint="Remove 'series' and use 'bases' or 'platforms'",
            )
        ]


class NamingConventions(Rule):
    """Flag config option names written with underscores.

    Charm config options are hyphenated by convention —
    ``juju config app log-level=debug`` — and an underscored name
    stands out at every point an operator types it. The name is part of
    the charm's interface, so this is worth fixing early: renaming an
    option later breaks everyone already setting it.

    Config options only. Juju rejects an underscored action name
    outright, so no charm has one to report, and underscored action
    parameters are vanishingly rare in the wild.
    """

    category = "CHARMCRAFT"
    number = 2
    name = "naming-conventions"
    description = "Config option names use underscores instead of hyphens"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-config"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                log_level:
                  type: string
                  default: info
                  description: Workload log level.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            config:
              options:
                log-level:
                  type: string
                  default: info
                  description: Workload log level.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # Juju/charmcraft reject underscored action names outright, and
        # underscored action parameters are vanishingly rare in the wild,
        # so this rule targets config options only.
        diagnostics: list[models.Diagnostic] = []
        for opt_name, option in context.config_options.items():
            if isinstance(opt_name, str) and "_" in opt_name:
                hyphenated = re.sub(r"[-_]+", "-", opt_name)
                diagnostics.append(
                    self.diagnostic(
                        f"Config option '{opt_name}' uses underscores — prefer hyphens ('{hyphenated}')",
                        path=option.source,
                        line=option.line,
                        fix_hint=f"Rename to '{hyphenated}'",
                    )
                )
        return diagnostics


class Entrypoint(Rule):
    """Check that a hand-written ``dispatch`` runs a real entrypoint.

    charmcraft generates ``dispatch`` at pack time, so most charm repos
    have none and the rule says nothing about them. A ``dispatch``
    committed to the repo is the charm author's own, and a mistake in
    it kills every hook: the entrypoint it names may not exist, may not
    be a regular file, or — when dispatch runs it directly rather than
    handing it to an interpreter — may not carry the executable bit.
    An entrypoint passed to ``python3`` needs no such bit, and is not
    reported for lacking one.

    Anything the script does not spell out statically is left alone: a
    command built from a shell variable, a path leading outside the
    charm, or a ``dispatch`` whose last statement does not run a
    ``.py`` file at all. A ``dispatch`` that cannot be read is an
    environment problem rather than the charm's, and is passed over
    too.
    """

    category = "CHARMCRAFT"
    number = 3
    name = "dispatch-entrypoint-issues"
    description = "Charm entrypoint missing or not executable"
    default_severity = models.Severity.ERROR
    reference_url = (
        "https://canonical.com/juju/docs/charmcraft/stable/reference/files/dispatch-file/"
    )
    example = {
        "charmcraft.yaml": """
            name: web-frontend
        """,
        "dispatch": """
            #!/bin/sh
            JUJU_DISPATCH_PATH="${JUJU_DISPATCH_PATH:-$0}" PYTHONPATH=lib:venv exec python3 ./src/main.py
        """,
        "src/charm.py": """
            import ops

            class WebFrontendCharm(ops.CharmBase):
                pass

            if __name__ == "__main__":
                ops.main(WebFrontendCharm)
        """,
    }
    fix = {
        "dispatch": """
            #!/bin/sh
            JUJU_DISPATCH_PATH="${JUJU_DISPATCH_PATH:-$0}" PYTHONPATH=lib:venv exec python3 ./src/charm.py
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        # charmcraft generates dispatch at pack time, so most charm repos do
        # not have one. Only a hand-written dispatch is worth checking.
        dispatch = context.charm_dir / "dispatch"
        if not dispatch.is_file():
            return []
        try:
            # Decoding never fails (errors="replace"), so this is only the
            # environmental cases — unreadable mode, I/O error — where the
            # charm itself is not at fault.
            content = dispatch.read_text(errors="replace")
        except OSError:
            return []

        resolved = self._entrypoint(content)
        if resolved is None:
            return []
        entrypoint_rel, via_interpreter = resolved
        entrypoint = context.charm_dir / entrypoint_rel

        if not entrypoint.exists():
            return [
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' referenced in dispatch does not exist",
                    path="dispatch",
                    fix_hint=f"Create {entrypoint_rel}, or point dispatch at the real entrypoint",
                )
            ]
        if not entrypoint.is_file():
            return [
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' referenced in dispatch is not a regular file",
                    path="dispatch",
                )
            ]
        # An entrypoint handed to an interpreter does not need the executable
        # bit — only one dispatch runs directly does.
        if not via_interpreter and not os.access(entrypoint, os.X_OK):
            return [
                self.diagnostic(
                    f"Entrypoint '{entrypoint_rel}' is not executable",
                    path=entrypoint_rel,
                    fix_hint=f"Run: chmod +x {entrypoint_rel}",
                )
            ]
        return []

    def _entrypoint(self, dispatch_content: str) -> tuple[str, bool] | None:
        """Resolve the entrypoint dispatch runs.

        Returns the charm-relative path and whether it is handed to an
        interpreter rather than executed directly, or ``None`` when dispatch
        does something too dynamic to resolve statically.
        """
        command_line = self._command_line(dispatch_content)
        if command_line is None:
            return None

        via_interpreter = False
        words = [word.strip("'\"") for word in command_line.split()]
        for index, word in enumerate(words):
            more_follow = index < len(words) - 1
            # A leading ``VAR=`` assignment, e.g. ``PYTHONPATH=lib:venv``.
            if re.match(r"^\w+=", word):
                continue
            # An interpreter run by name: ``python``, ``python3``,
            # ``python3.12``, or ``/usr/bin/env`` (matched on basename).
            if more_follow and re.match(
                r"^(?:python[0-9.]*|env)$", pathlib.PurePosixPath(word).name
            ):
                via_interpreter = True
                continue
            # An interpreter named by a variable, e.g. ``$PYTHON_BIN charm.py``:
            # unresolvable as a command, but its argument is still the charm.
            if more_follow and "$" in word:
                via_interpreter = True
                continue
            relative = self._charm_relative(word)
            return None if relative is None else (relative, via_interpreter)
        return None

    def _command_line(self, dispatch_content: str) -> str | None:
        """Return the dispatch line that runs the charm, sans any ``exec``."""
        # The command dispatch hands control to, e.g. the ``./src/charm.py``
        # in ``PYTHONPATH=lib:venv exec ./src/charm.py``. Stops at a shell
        # separator so a trailing redirect or ``&&`` is not swallowed in.
        match = re.search(r"\bexec\s+(?P<rest>[^\n;&|<>]+)", dispatch_content)
        if match is not None:
            return match.group("rest")
        # No ``exec``: hand-written dispatch scripts often just run the charm
        # as their last statement. Only the last statement is considered, so a
        # ``.py`` path mentioned earlier in the script is not mistaken for the
        # entrypoint.
        for line in reversed(dispatch_content.splitlines()):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return line if ".py" in line else None
        return None

    def _charm_relative(self, command: str) -> str | None:
        """Normalise a dispatch command to a charm-relative path, if it is one."""
        # Anything with shell expansion in it, or pointing outside the charm,
        # cannot be resolved statically.
        if not command or "$" in command or "`" in command:
            return None
        path = pathlib.PurePosixPath(command)
        if path.is_absolute() or ".." in path.parts:
            return None
        parts = [part for part in path.parts if part != "."]
        return str(pathlib.PurePosixPath(*parts)) if parts else None


class UnknownTopLevelField(Rule):
    """Flag unrecognised top-level keys in charmcraft.yaml or metadata.yaml.

    Catches typos like ``sumary`` instead of ``summary`` that would otherwise
    go silently unnoticed. Only top-level keys are checked; user-defined
    sub-keys inside ``config.options``, ``actions``, ``requires``, etc. are
    left alone because their names are charm-specific.
    """

    category = "CHARMCRAFT"
    number = 4
    name = "unknown-top-level-field"
    description = "Unrecognised top-level field in charm metadata (possible typo)"
    default_severity = models.Severity.WARNING
    reference_url = (
        "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/"
    )
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
            sumary: Serves the web frontend.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
            summary: Serves the web frontend.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for key, field in context.metadata.items():
            # A charm may split its metadata across both files, in which case
            # each key is judged against the set for the file it came from.
            source = field.source
            known = (
                _KNOWN_METADATA_FIELDS if source == "metadata.yaml" else _KNOWN_CHARMCRAFT_FIELDS
            )
            if key in known:
                continue
            # A key that is valid in the *other* file is a misplaced field
            # rather than a typo, and saying so is more useful than a
            # "did you mean" hint that has nothing close to suggest.
            other = (
                _KNOWN_CHARMCRAFT_FIELDS if source == "metadata.yaml" else _KNOWN_METADATA_FIELDS
            )
            if key in other:
                other_source = "charmcraft.yaml" if source == "metadata.yaml" else "metadata.yaml"
                message = f"Field '{key}' is valid in {other_source} but not {source}"
                fix_hint = None
            else:
                message = f"Unrecognised top-level field '{key}' in {source} — possible typo"
                fix_hint = _suggest_closest(key, known)
            diagnostics.append(
                self.diagnostic(
                    message,
                    path=source,
                    line=field.line,
                    fix_hint=fix_hint,
                )
            )
        return diagnostics


class UnknownResourceField(Rule):
    """Flag unrecognised keys inside resource definitions."""

    category = "CHARMCRAFT"
    number = 5
    name = "unknown-resource-field"
    description = "Unrecognised field inside a resource definition (possible typo)"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-resources"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            resources:
              frontend-image:
                type: oci-image
                descripton: OCI image for the frontend container.
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            resources:
              frontend-image:
                type: oci-image
                description: OCI image for the frontend container.
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for res_name, resource in context.metadata.get("resources").items():
            for key, field in resource.items():
                if key not in _KNOWN_RESOURCE_FIELDS:
                    diagnostics.append(
                        self.diagnostic(
                            f"Unrecognised field '{key}' in resource '{res_name}' — possible typo",
                            path=field.source,
                            line=field.line,
                            fix_hint=_suggest_closest(key, _KNOWN_RESOURCE_FIELDS),
                        )
                    )
        return diagnostics


class OpsMainCall(Rule):
    """Check that a charm's entrypoint calls ``ops.main()``.

    Only the single file charmcraft designates as the entrypoint is
    examined — ``parts.charm.charm-entrypoint``, or ``src/charm.py``
    when unset. That is the file ``dispatch`` runs, so it is the only
    one whose module-level code Juju executes: an ``ops.main()`` call in
    a sibling module never runs unless the entrypoint imports it.

    Charms whose entrypoint is not a collected Python file (a shell
    wrapper, or a console script installed as a dependency) are skipped
    rather than flagged — there is no charm source here to judge.
    """

    category = "CHARMCRAFT"
    number = 6
    name = "no-ops-main-call"
    description = "Charm entrypoint does not call ops.main()"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/ops/latest/reference/ops-main-entrypoint/"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
        """,
        "src/charm.py": """
            import ops

            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._on_start)

                def _on_start(self, event: ops.StartEvent):
                    self.unit.status = ops.ActiveStatus()
        """,
    }
    fix = {
        "src/charm.py": """
            import ops

            class WebFrontendCharm(ops.CharmBase):
                def __init__(self, framework: ops.Framework):
                    super().__init__(framework)
                    framework.observe(self.on.start, self._on_start)

                def _on_start(self, event: ops.StartEvent):
                    self.unit.status = ops.ActiveStatus()

            if __name__ == "__main__":
                ops.main(WebFrontendCharm)
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        entrypoint = _entrypoint(context)
        module = next((m for m in context.modules() if m.path == entrypoint), None)
        if module is None:
            return []
        imports = _ast.Imports.of(module)
        # A charm that doesn't use ops has nothing to say about ops.main().
        if not imports.imports_module("ops"):
            return []
        for call in module.walk(ast.Call):
            if _ast.call_target(call, imports) in _OPS_MAIN_TARGETS:
                return []
        return [
            self.diagnostic(
                "Charm entrypoint imports ops but never calls ops.main()",
                path=module.path,
                fix_hint="Add `ops.main(MyCharm)` at the end of the charm entrypoint",
            )
        ]


class CharmUser(Rule):
    """Check a Kubernetes charm's ``charm-user`` declaration.

    ``charm-user`` says what kind of user Juju runs the charm's hook
    code as. It is one of ``root``, ``sudoer`` or ``non-root``, and Juju
    assumes ``root`` when it is not set, so a Kubernetes charm that says
    nothing runs its hooks with full privileges.

    The advisory findings are limited to Kubernetes charms, because the
    key has no effect on a machine charm. An invalid *value* is reported
    wherever it appears: it is a malformed key rather than a question of
    privilege.
    """

    category = "CHARMCRAFT"
    number = 8
    name = "charm-user"
    description = "Kubernetes charm runs its hooks as root, or declares an invalid 'charm-user'"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-charm-user"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            containers:
              frontend:
                resource: frontend-image
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            charm-user: non-root
            containers:
              frontend:
                resource: frontend-image
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        node = context.metadata.get("charm-user")
        value = node.value
        if node.present and (not isinstance(value, str) or value not in _VALID_CHARM_USERS):
            hint = _suggest_closest(value, _VALID_CHARM_USERS) or (
                "Use 'root', 'sudoer' or 'non-root'"
            )
            return [
                self.diagnostic(
                    f"'charm-user' is {value!r} — it must be one of 'root', 'sudoer' or 'non-root'",
                    severity=models.Severity.ERROR,
                    path=node.source,
                    line=node.line,
                    fix_hint=hint,
                )
            ]
        if not _is_kubernetes_charm(context):
            return []
        if not node.present:
            return [
                self.diagnostic(
                    "Kubernetes charm does not set 'charm-user', so Juju runs its hooks as root",
                    path=context.metadata.source,
                    fix_hint=(
                        "Add `charm-user: non-root` (or `sudoer`) to charmcraft.yaml — "
                        f"{_NON_ROOT_SKILL}"
                    ),
                )
            ]
        if value == "root":
            return [
                self.diagnostic(
                    "'charm-user: root' runs the charm's hooks as root",
                    path=node.source,
                    line=node.line,
                    fix_hint=(
                        "Use `charm-user: non-root` (or `sudoer`) unless the hooks need root — "
                        f"{_NON_ROOT_SKILL}"
                    ),
                )
            ]
        if value == "sudoer":
            return [
                self.diagnostic(
                    "'charm-user: sudoer' runs the charm's hooks as a user that can elevate "
                    "to root through sudo",
                    severity=models.Severity.INFO,
                    path=node.source,
                    line=node.line,
                    fix_hint="Use `charm-user: non-root` if the hooks never need to elevate",
                )
            ]
        return []


class ContainerRunsAsRoot(Rule):
    """Check the ``uid``/``gid`` of each workload container.

    Juju runs a container's Pebble entry process as the ``uid`` and
    ``gid`` the container declares, defaulting both to 0 — so a
    container that leaves them out, or sets them to 0, runs its workload
    as root. Juju also reserves 1000-9999 for its own users: a value in
    that range is rejected rather than honoured.

    A container that is non-root but off-convention is reported more
    quietly. ``uid`` and ``gid`` that disagree are a warning: the two are
    written together and a mismatch is almost always a typo, and it
    leaves the process in a group the image never prepared for. An ID
    that is not 584792 is only an info — it works, but 584792 is the
    shared ``_daemon_`` user rocks are built around, so anything else
    means the image has to have been built to match. 584788 is the
    exception: it is the deprecated ``snap_daemon`` that ``_daemon_``
    replaced, so a container still on it is on the old identity rather
    than an arbitrary one, and that is a warning.

    A container written as anything other than a mapping is skipped, the
    same as elsewhere in this module: a malformed section is not a
    privilege finding.
    """

    category = "CHARMCRAFT"
    number = 9
    name = "container-runs-as-root"
    description = (
        "Workload container runs as root, has mismatched uid/gid, or uses a nonstandard identity"
    )
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-containers"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            containers:
              frontend:
                resource: frontend-image
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            containers:
              frontend:
                resource: frontend-image
                uid: 584792
                gid: 584792
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        diagnostics: list[models.Diagnostic] = []
        for name, container in context.metadata.get("containers").items():
            if container.children is None:
                continue
            diagnostics.extend(self._check_container(name, container))
        return diagnostics

    def _check_container(self, name: object, container: models.Yaml) -> list[models.Diagnostic]:
        """Report on one container's ``uid`` and ``gid``."""
        diagnostics: list[models.Diagnostic] = []
        root: dict[str, str] = {}
        ids: dict[str, int] = {}
        for key in ("uid", "gid"):
            node = container.get(key)
            if not node.present:
                root[key] = f"'{key}' is unset, defaulting to 0"
                continue
            invalid = self._invalid_reason(node.value)
            if invalid is not None:
                diagnostics.append(
                    self.diagnostic(
                        f"Container '{name}' has {key} {node.value!r} — {invalid}",
                        severity=models.Severity.ERROR,
                        path=node.source,
                        line=node.line,
                        fix_hint=(
                            f"Use {_DAEMON_ID}, the shared '_daemon_' user rocks run as; "
                            "Juju accepts 1-999 and 10000 and above"
                        ),
                    )
                )
            elif node.value == 0:
                root[key] = f"'{key}' is 0"
            elif isinstance(node.value, int):
                ids[key] = node.value
        if root:
            # Anchor on whichever of the two the charm wrote, so a noqa
            # directive sits on the line the reader is looking at; a
            # container that declares neither anchors on its own name.
            line = next(
                (container.get(key).line for key in ("uid", "gid") if container.get(key).present),
                container.line,
            )
            lead = "as root" if "uid" in root else "in the root group"
            detail = " and ".join(root[key] for key in ("uid", "gid") if key in root)
            diagnostics.append(
                self.diagnostic(
                    f"Container '{name}' runs its Pebble entry process {lead} — {detail}",
                    path=container.source,
                    line=line,
                    fix_hint=(
                        f"Set 'uid' and 'gid' on container '{name}' to {_DAEMON_ID}, the shared "
                        f"'_daemon_' user rocks run as — {_NON_ROOT_SKILL}"
                    ),
                )
            )
            return diagnostics
        if len(ids) < 2:
            # One of the two was invalid; that error stands on its own.
            return diagnostics
        uid, gid = ids["uid"], ids["gid"]
        if uid != gid:
            diagnostics.append(
                self.diagnostic(
                    f"Container '{name}' has uid {uid} and gid {gid} — the two should match",
                    path=container.source,
                    line=container.get("uid").line,
                    fix_hint=(
                        f"Set both 'uid' and 'gid' on container '{name}' to {_DAEMON_ID}, the "
                        "shared '_daemon_' user rocks run as"
                    ),
                )
            )
        elif uid == _SNAP_DAEMON_ID:
            diagnostics.append(
                self.diagnostic(
                    f"Container '{name}' runs as {uid}, the deprecated 'snap_daemon' user — "
                    f"{_DAEMON_ID} ('_daemon_') replaces it",
                    severity=models.Severity.WARNING,
                    path=container.source,
                    line=container.get("uid").line,
                    fix_hint=(
                        f"Set 'uid' and 'gid' on container '{name}' to {_DAEMON_ID} once the "
                        f"image is rebuilt with '_daemon_' — {_NON_ROOT_SKILL}"
                    ),
                )
            )
        elif uid != _DAEMON_ID:
            diagnostics.append(
                self.diagnostic(
                    f"Container '{name}' runs as {uid}, not {_DAEMON_ID} — the shared "
                    "'_daemon_' user rocks are built around",
                    severity=models.Severity.INFO,
                    path=container.source,
                    line=container.get("uid").line,
                    fix_hint=(
                        f"Set 'uid' and 'gid' on container '{name}' to {_DAEMON_ID} unless the "
                        f"image was built for {uid} — {_NON_ROOT_SKILL}"
                    ),
                )
            )
        return diagnostics

    def _invalid_reason(self, value: object) -> str | None:
        """Return why *value* is not a usable ID, or ``None`` if it is.

        ``bool`` is excluded explicitly: it is a subclass of ``int``, so
        an unquoted ``uid: yes`` would otherwise pass as 1.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            return "IDs must be integers"
        if value < 0:
            return "IDs cannot be negative"
        if 1000 <= value <= 9999:
            return "Juju reserves 1000-9999 for users; use 1-999 or 10000 and above"
        return None


# --- Helpers ---------------------------------------------------------------


class LegacyBases(Rule):
    """Flag the charmcraft 2 ``bases:`` block.

    ``base:`` plus ``platforms:`` is the form charmcraft documents and the
    one that expresses everything ``bases:`` could. How much of a problem
    the old block is depends on the release it names: ``bases`` is only
    accepted for bases supported before 2024-01-01, so a charm that names
    24.04 or later there will not pack at all, while one still on 22.04
    builds fine and has only migration ahead of it. Reported as a warning
    in the first case and info in the second.
    """

    category = "CHARMCRAFT"
    number = 7
    name = "legacy-bases"
    description = "Legacy 'bases' block instead of 'base' and 'platforms'"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-platforms"
    example = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                run-on:
                  - name: ubuntu
                    channel: "22.04"
        """,
    }
    fix = {
        "charmcraft.yaml": """
            name: web-frontend
            type: charm
            base: ubuntu@22.04
            platforms:
              amd64:
        """,
    }

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        bases = context.metadata.get("bases")
        # ``bases`` is a charmcraft.yaml key. A stray one in metadata.yaml is
        # dead text charmcraft ignores — several charms in the wild have
        # migrated charmcraft.yaml to platforms and left the old block behind
        # — so telling those charms to migrate would be wrong.
        if not bases.present or bases.source != "charmcraft.yaml":
            return []
        unsupported = any(
            (year := _release_year(channel)) is not None and year >= _FIRST_UNSUPPORTED_YEAR
            for channel in _base_channels(bases)
        )
        if unsupported:
            message = (
                "'bases' is not accepted for Ubuntu 24.04 and later — charmcraft "
                "will refuse to pack; use 'base' and 'platforms' instead"
            )
            severity = models.Severity.WARNING
        else:
            message = "'bases' is the charmcraft 2 form — use 'base' and 'platforms' instead"
            severity = models.Severity.INFO
        return [
            self.diagnostic(
                message,
                severity=severity,
                path=bases.source,
                line=bases.line,
                fix_hint="Replace 'bases' with a 'base' key and a 'platforms' block",
            )
        ]


def _entrypoint(context: models.CharmContext) -> str:
    """Return the charm-relative path of the entrypoint charmcraft will use.

    The charm plugin's ``charm-entrypoint`` names the file ``dispatch``
    execs, relative to the project directory; charmcraft defaults it to
    ``src/charm.py``. The value is a plain string in charmcraft.yaml, so
    anything else (a list, say) falls back to the default.
    """
    configured = context.metadata.get("parts").get("charm").get("charm-entrypoint").value
    if not isinstance(configured, str) or not configured:
        configured = "src/charm.py"
    return pathlib.PurePosixPath(configured).as_posix()


_VALID_CHARM_USERS: frozenset[str] = frozenset({"root", "sudoer", "non-root"})

# The shared ``_daemon_`` user, allocated for snaps and rocks alike so that a
# workload has one identity wherever it runs. See
# https://discourse.ubuntu.com/t/unifying-user-identity-across-snaps-and-rocks/36469
_DAEMON_ID = 584792

# The predecessor of ``_daemon_``, deprecated in favour of it. A container
# still on this ID is on the old identity rather than an arbitrary one. See
# https://snapcraft.io/docs/explanation/snap-development/system-usernames/#snap-daemon-user-and-group
_SNAP_DAEMON_ID = 584788

# Named in the hints for the findings that amount to "migrate this charm to
# non-root", which is more work than a one-line edit: the skill walks the
# charm, its containers and its rocks.
_NON_ROOT_SKILL = (
    "the non-root-charms skill (https://github.com/deusebio/non-root-skills) automates this"
)


def _is_kubernetes_charm(context: models.CharmContext) -> bool:
    """Return whether the charm is a Kubernetes charm.

    A sidecar charm declares the workload containers it sits beside, so
    ``containers`` is the reliable signal, and ``assumes: [k8s-api]``
    covers the charm that has no container of its own but still targets
    Kubernetes. Neither is guaranteed, so a Kubernetes charm that
    declares nothing at all reads as a machine charm here — a gap,
    rather than a machine charm wrongly told to change its metadata.

    A pod-spec charm (``series: [kubernetes]``) is deliberately not
    matched: ``charm-user`` arrived in Juju 3.6, by which point pod-spec
    charms were no longer deployable, so there is nothing such a charm
    could do about the finding.
    """
    if context.metadata.get("containers").children:
        return True
    return _assumes_k8s(context.metadata.get("assumes").value)


def _assumes_k8s(assumes: object) -> bool:
    """Return whether an ``assumes`` block requires the Kubernetes API.

    The block nests ``any-of``/``all-of`` mappings around its feature
    strings to any depth, and either branch of an ``any-of`` may be the
    Kubernetes one, so every leaf counts.
    """
    if isinstance(assumes, str):
        return assumes == "k8s-api"
    if isinstance(assumes, list):
        return any(_assumes_k8s(item) for item in assumes)
    if isinstance(assumes, dict):
        return any(_assumes_k8s(item) for item in assumes.values())
    return False


# Every spelling of the ops entrypoint, canonicalised: ``ops.main`` is the
# submodule and the function of the same name inside it, and both are
# callable. ``_ast.Imports`` resolves the aliases, so ``main(MyCharm)``
# after ``from ops import main`` lands on ``ops.main`` like the rest.
_OPS_MAIN_TARGETS = frozenset({"ops.main", "ops.main.main"})


# Top-level keys valid in charmcraft.yaml (modern and legacy forms). A
# separate set is kept for metadata.yaml below, because the two files accept
# different top-level keys.
# Kept deliberately broad — a false positive on a genuine field is far
# worse than missing a truly unknown one.
# The modern keys mirror charmcraft's published schema/charmcraft.json, plus
# legacy keys the schema has dropped. Hand-maintained for now; see #174 for
# validating against that schema directly instead.
_KNOWN_CHARMCRAFT_FIELDS: frozenset[str] = frozenset(
    {
        # Identity / metadata.
        "name",
        "type",
        "title",
        "summary",
        "description",
        # Build / platform.
        "base",
        "build-base",
        "bases",
        "platforms",
        "parts",
        "extensions",
        "adopt-info",
        "package-repositories",
        # Relations.
        "requires",
        "provides",
        "peers",
        "extra-bindings",
        # Config / actions.
        "config",
        "actions",
        # Workload.
        "containers",
        "resources",
        "storage",
        "devices",
        # Charm libraries and dependencies.
        "charm-libs",
        # Workload run-as user (Kubernetes charms).
        "charm-user",
        # Links block (Charmhub) — nested form, e.g. links.documentation.
        "links",
        # Legacy top-level contact (now links.contact).
        "contact",
        # Subordinate / assumes.
        "subordinate",
        "assumes",
        "terms",
        # Legacy (deprecated but still accepted).
        "series",
        "min-juju-version",
        "charmhub",
        # Analysis / linting config inside the file.
        "analysis",
    }
)

# Keys that configure how the charm is *built*. These are meaningful only in
# charmcraft.yaml, so they stay unknown in metadata.yaml.
_BUILD_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "parts",
        "base",
        "build-base",
        "extensions",
        "adopt-info",
        "package-repositories",
        "analysis",
        "charmhub",
    }
)

# Keys valid in metadata.yaml but not charmcraft.yaml. metadata.yaml uses flat
# top-level link fields instead of a nested links block, and
# display-name/maintainers instead of title/links.contact.
_METADATA_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "display-name",
        # Top-level link fields (no nested links block).
        "docs",
        "issues",
        "source",
        "website",
        # Both the list form and the singular string form are valid.
        "maintainers",
        "maintainer",
        # Charmhub categorisation ('categories' predates 'tags').
        "tags",
        "categories",
        # Kubernetes deployment block (type / service).
        "deployment",
        # Legacy (deprecated but still accepted).
        "format",
        "version",
    }
)

# Top-level keys valid in metadata.yaml (the separate legacy metadata file).
# Everything that describes the charm itself is valid in either file — a charm
# that splits its metadata may put those keys on either side — so only the
# build-only keys above are charmcraft.yaml-exclusive.
_KNOWN_METADATA_FIELDS: frozenset[str] = _METADATA_ONLY_FIELDS | (
    _KNOWN_CHARMCRAFT_FIELDS - _BUILD_ONLY_FIELDS
)

# Keys recognised inside a ``resources.<name>`` block.
_KNOWN_RESOURCE_FIELDS: frozenset[str] = frozenset(
    {
        "type",
        "description",
        "filename",
        "upstream-source",
    }
)


# ``bases`` is only accepted for bases supported before 2024-01-01, so every
# Ubuntu release from 24.04 on is out — which is every channel whose year is
# 24 or later, there being no release earlier in 2024 than 24.04.
_FIRST_UNSUPPORTED_YEAR = 24


def _base_channels(bases: models.Yaml) -> Iterator[object]:
    """Yield every channel named under a ``bases`` block.

    Both forms are covered: the flat ``name``/``channel`` entry, and the
    ``build-on``/``run-on`` entry whose sub-lists hold the entries instead.
    """
    for entry in bases.elements or ():
        channel = entry.get("channel")
        if channel.present:
            yield channel.value
        for key in ("build-on", "run-on"):
            for sub_entry in entry.get(key).elements or ():
                sub_channel = sub_entry.get("channel")
                if sub_channel.present:
                    yield sub_channel.value


def _release_year(channel: object) -> int | None:
    """Return the year of an Ubuntu channel such as ``22.04``, if it has one.

    Channels are conventionally quoted, but an unquoted ``channel: 22.04``
    parses as a float, so the value is matched as text either way. Only the
    year is taken: every release in a year falls the same side of the 2024
    cut-off, and an unquoted ``24.10`` would reach here as ``24.1`` anyway.
    """
    match = re.match(r"(\d\d)\.\d", str(channel).strip())
    if match is None:
        return None
    return int(match[1])


def _suggest_closest(typo: object, known: frozenset[str]) -> str | None:
    """Return a ``Did you mean 'X'?`` hint if a close match exists."""
    # YAML keys are not necessarily strings: an unquoted `on:` parses to a
    # bool, and a bare numeric key to an int. Those get flagged, but no hint.
    if not isinstance(typo, str):
        return None
    best: list[str] = []
    best_dist = 2  # Only suggest if edit distance <= 2.
    # Sorted so that equally-close candidates are listed in a stable order:
    # `known` is a frozenset, whose iteration order varies with PYTHONHASHSEED.
    for candidate in sorted(known):
        # `best_dist + 1` as the threshold, so that anything at or below
        # `best_dist` is an exact distance rather than an early bail-out.
        d = _edit_distance(typo, candidate, best_dist + 1)
        if d > best_dist:
            continue
        if d < best_dist:
            best_dist = d
            best = []
        best.append(candidate)
    if not best:
        return None
    quoted = [f"'{c}'" for c in best]
    if len(quoted) > 1:
        quoted[-1] = f"or {quoted[-1]}"
    joined = " ".join(quoted) if len(quoted) == 2 else ", ".join(quoted)
    return f"Did you mean {joined}?"


def _edit_distance(a: str, b: str, threshold: int) -> int:
    """Levenshtein distance, bailing out early if it exceeds *threshold*."""
    if abs(len(a) - len(b)) >= threshold:
        return threshold
    # Standard two-row DP.
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1] + [0] * len(b)
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr[j + 1] = min(prev[j + 1] + 1, curr[j] + 1, prev[j] + cost)
        prev = curr
    return prev[len(b)]
