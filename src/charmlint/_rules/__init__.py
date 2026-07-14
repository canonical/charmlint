"""Rule package — re-exports the base class and triggers rule registration."""

from . import charmcraft_compat as _charmcraft_compat  # noqa: F401  (import registers rules)
from . import documentation as _documentation  # noqa: F401  (import registers rules)
from . import metadata as _metadata  # noqa: F401  (import registers rules)
from ._base import Rule, get_all_rules

__all__ = ["Rule", "get_all_rules"]
