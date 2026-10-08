"""Rule package — re-exports the base class and triggers rule registration."""

# Importing each rule module registers its Rule subclasses via the metaclass
# in ._base — the private names below are unused, hence the unused-import suppressions.
from . import actions as _actions  # ruff: ignore[unused-import]
from . import charmcraft_compat as _charmcraft_compat  # ruff: ignore[unused-import]
from . import config_quality as _config_quality  # ruff: ignore[unused-import]
from . import correctness as _correctness  # ruff: ignore[unused-import]
from . import documentation as _documentation  # ruff: ignore[unused-import]
from . import features as _features  # ruff: ignore[unused-import]
from . import libraries as _libraries  # ruff: ignore[unused-import]
from . import metadata as _metadata  # ruff: ignore[unused-import]
from . import pebble as _pebble  # ruff: ignore[unused-import]
from . import security as _security  # ruff: ignore[unused-import]
from . import status as _status  # ruff: ignore[unused-import]
from . import structure as _structure  # ruff: ignore[unused-import]
from . import supplychain as _supplychain  # ruff: ignore[unused-import]
from . import testing as _testing  # ruff: ignore[unused-import]
from ._base import CATEGORIES, Rule, get_all_rules

__all__ = ["CATEGORIES", "Rule", "get_all_rules"]
