"""Correctness rules — runtime-correctness issues in charm source."""

import re

from .. import models
from . import Rule


class StorageWithoutAttachedObserver(Rule):
    """Flag declared storage entries with no ``*_storage_attached`` observer.

    Without observing the ``<name>-storage-attached`` event, a charm cannot
    react to ``juju add-storage`` after deployment — the storage is mounted
    but the charm never gets a chance to format/configure it.
    """

    id = "CORR002"
    name = "storage-without-attached-observer"
    description = "Storage declared in charmcraft.yaml without a *_storage_attached event observer"
    default_severity = models.Severity.WARNING

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        storage_section = context.metadata.get("storage")
        if not isinstance(storage_section, dict) or not storage_section:
            return []

        # Concatenate all non-lib Python source — observers are typically in
        # __init__, but accept any module to avoid false positives from charms
        # that delegate observer registration to a helper.
        sources: list[str] = []
        for path, content in context.python_sources.items():
            if "lib" in path.parts:
                continue
            sources.append(content)
        combined = "\n".join(sources)

        diagnostics: list[models.Diagnostic] = []
        for storage_name in storage_section:
            if not isinstance(storage_name, str):
                continue
            normalised = storage_name.replace("-", "_")
            pattern = re.compile(
                r"\.observe\s*\(\s*self\.on\." + re.escape(normalised) + r"_storage_attached\b"
            )
            if pattern.search(combined):
                continue
            diagnostics.append(
                self.diagnostic(
                    f"Storage '{storage_name}' is declared in charmcraft.yaml but no "
                    f"observer for the '{storage_name}-storage-attached' event was "
                    f"found — the charm will not react to `juju add-storage` after "
                    f"deployment",
                    path="charmcraft.yaml",
                    fix_hint=(
                        f"Add `self.framework.observe(self.on.{normalised}_storage_attached, "
                        f"self._on_{normalised}_storage_attached)` in __init__"
                    ),
                )
            )
        return diagnostics
