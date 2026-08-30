"""Rule package — re-exports the base class and triggers rule registration."""

# Importing each rule module registers its Rule subclasses via the metaclass
# in ._base — the private names below are unused, hence the F401 suppressions.
from . import actions as _actions  # noqa: F401
from . import charmcraft_compat as _charmcraft_compat  # noqa: F401
from . import config_quality as _config_quality  # noqa: F401
from . import documentation as _documentation  # noqa: F401
from . import libraries as _libraries  # noqa: F401
from . import metadata as _metadata  # noqa: F401
from . import pebble as _pebble  # noqa: F401
from . import security as _security  # noqa: F401
from . import structure as _structure  # noqa: F401
from . import supply_chain as _supply_chain  # noqa: F401
from . import testing as _testing  # noqa: F401
from ._base import Rule, get_all_rules

__all__ = ["Rule", "get_all_rules"]
