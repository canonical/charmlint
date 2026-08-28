"""Loading a charm's YAML files into provenance-carrying trees.

One pass over the composed node tree produces both the values and the
line each key sits on, so there is a single place that knows how a
charm's YAML is read. Rules ask a value where it came from
(:class:`~charmlint._models.Yaml`) rather than looking its line up in a
side table that the linter core had to build for that section in
advance.
"""

import pathlib
from typing import Any

import yaml

from . import _models as models

# Use the libyaml-backed C loader when available — it's ~10× faster than
# the pure-Python SafeLoader and matches what ops does internally.
_SafeLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class FileLoadError(Exception):
    """Raised when a required file exists but cannot be loaded.

    Covers YAML syntax errors, OS-level read failures, and any other
    failure to turn a present file into usable data. Distinct from the
    absent-file case so the linter can tell the user which file is
    broken instead of falsely claiming the manifest is missing.
    """

    def __init__(self, path: pathlib.Path, reason: str) -> None:
        super().__init__(f"{path.name}: {reason}")
        self.path = path
        self.reason = reason


def load(path: pathlib.Path) -> models.Yaml:
    """Load a YAML file into a :class:`~charmlint._models.Yaml` tree.

    Returns an absent node only when *path* does not exist. Every other
    failure (unreadable file, YAML syntax error, top-level value that
    isn't a mapping) is surfaced via :class:`FileLoadError` — a file
    that is there but broken should never be silently reported as
    missing.

    Composing the document rather than re-implementing a parser keeps
    line numbers correct through comments, block scalars, and anchors.
    """
    source = path.name
    if not path.exists():
        return models.Yaml.absent(source)
    try:
        with path.open() as f:
            loader = _SafeLoader(f)
            try:
                node = loader.get_single_node()
                root = None if node is None else _build(node, loader, source, line=None)
            finally:
                loader.dispose()
    except yaml.YAMLError as exc:
        raise FileLoadError(path, str(exc)) from exc
    except OSError as exc:
        raise FileLoadError(path, f"could not read: {exc}") from exc
    except TypeError as exc:
        # An unhashable mapping key (``[a, b]: c``). PyYAML raises a
        # ConstructorError for this when it builds the mapping itself;
        # building it here surfaces it as a TypeError instead.
        raise FileLoadError(path, f"invalid mapping key: {exc}") from exc
    except RecursionError as exc:
        # A self-referential anchor (``links: &a\n  - *a``). Walking the
        # composed tree runs out of stack where PyYAML's own constructor
        # would have refused the document; report it the same way.
        raise FileLoadError(path, "found unconstructable recursive node") from exc
    # An empty file composes to nothing, which is the same "no metadata
    # here" state as a file that isn't there at all.
    if root is None:
        return models.Yaml.absent(source)
    if not isinstance(root.value, dict):
        raise FileLoadError(path, "top-level YAML value is not a mapping")
    return root


def merge(primary: models.Yaml, fallback: models.Yaml) -> models.Yaml:
    """Merge two metadata mappings, *primary* winning on duplicate keys.

    Keys present only in *fallback* are merged in, each keeping its own
    ``source`` and ``line`` — so a rule reporting on a merged-in key
    points at the file that actually declares it. This matches
    charmcraft's own behaviour for split-metadata charms.
    """
    if not fallback.children:
        return primary
    if not primary.children:
        return fallback
    children = dict(primary.children)
    for key, node in fallback.children.items():
        children.setdefault(key, node)
    return models.Yaml(
        value={key: node.value for key, node in children.items()},
        source=primary.source,
        line=primary.line,
        children=children,
    )


def _build(node: yaml.Node, loader: Any, source: str, line: int | None) -> models.Yaml:
    """Wrap a composed YAML node, recursing into mappings and sequences.

    *line* is the line to attribute the value to: for a mapping entry
    that is the line of its **key**, not of its value. A ``# noqa``
    comment sits on the option's own line (``admin-password:``),
    whereas the value's nested mapping begins on the following line.

    A sequence element has no key, so it is attributed to its own line.
    A block sequence therefore gives each element a distinct line, and a
    flow sequence (``[a, b]``) gives every element the line they share —
    which is the line a ``# noqa`` for any of them would sit on anyway.
    """
    if isinstance(node, yaml.SequenceNode):
        elements = [_build(item, loader, source, item.start_mark.line + 1) for item in node.value]
        return models.Yaml(
            value=[element.value for element in elements],
            source=source,
            line=line,
            elements=elements,
        )
    if not isinstance(node, yaml.MappingNode):
        return models.Yaml(
            value=loader.construct_object(node, deep=True), source=source, line=line
        )
    children: dict[Any, models.Yaml] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        # Later duplicates win, as they do in PyYAML's own constructor.
        children[key] = _build(value_node, loader, source, key_node.start_mark.line + 1)
    return models.Yaml(
        value={key: child.value for key, child in children.items()},
        source=source,
        line=line,
        children=children,
    )
