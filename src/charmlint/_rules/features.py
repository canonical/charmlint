"""Feature rules — expected charm features that are commonly missing."""

import re

from .. import models
from . import Rule

_BACKUP_RESTORE_RE = re.compile(r"backup|restore|export|import", re.IGNORECASE)


class StatefulNoBackupRestore(Rule):
    """Flag charms that declare peers but provide no backup/restore-like actions."""

    id = "FEAT008"
    name = "stateful-no-backup-restore-actions"
    description = "Charm declares peers but provides no backup/restore actions"
    default_severity = models.Severity.INFO

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        peers = context.metadata.get("peers")
        if not isinstance(peers, dict) or not peers:
            return []
        for action_name in context.actions:
            if _BACKUP_RESTORE_RE.search(action_name):
                return []
        return [
            self.diagnostic(
                "Charm declares `peers:` (suggesting stateful workload) but defines "
                "no backup/restore/export/import actions — operators have no way to "
                "back up or restore state",
                fix_hint=(
                    "Add `create-backup` and `restore-backup` actions (or equivalent "
                    "export/import actions) to charmcraft.yaml and implement handlers"
                ),
            )
        ]
