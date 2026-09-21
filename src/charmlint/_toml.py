"""Loading a charm's TOML files.

The third sibling to :mod:`charmlint._yaml` and :mod:`charmlint._ast`:
one place that knows how a charm's ``pyproject.toml`` is read, so a
rule receives data the linter core has already parsed rather than
reaching for the disk and inventing its own answer to "what if this
file is broken?".

Unlike the YAML loader this returns plain dictionaries rather than
provenance-carrying nodes. ``tomllib`` discards positions, so there is
no line number to carry; giving a rule a :class:`~charmlint._models.Yaml`
whose ``line`` was always ``None`` would promise provenance the parser
cannot supply. A rule reporting on ``pyproject.toml`` anchors to the
file. Wiring up real line numbers would mean a positions-preserving
TOML parser, which is a bigger change than any current rule justifies.
"""

import pathlib
import tomllib
from typing import Any

# FileLoadError is the linter core's "this file is present but broken"
# signal, raised for Python sources as much as for YAML. It lives in
# _yaml because that is where the first caller needed it.
from ._yaml import FileLoadError


def load(path: pathlib.Path) -> dict[str, Any] | None:
    """Load a TOML file, returning ``None`` when it does not exist.

    Every other failure (unreadable file, TOML syntax error) is
    surfaced via :class:`~charmlint._yaml.FileLoadError`, which the
    linter reports as a single ``FATAL`` naming the broken file. A
    malformed ``pyproject.toml`` swallowed here would instead reach
    each rule as "no dependencies declared", which is indistinguishable
    from a charm that genuinely declares none — a clean report for a
    charm nobody actually checked.
    """
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise FileLoadError(path, f"could not parse: {exc}") from exc
    except OSError as exc:
        raise FileLoadError(path, f"could not read: {exc}") from exc
