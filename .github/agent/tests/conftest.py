"""The agent's scripts aren't a package; import them as the workflow runs them."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
