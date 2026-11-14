"""Grep the charms in the corpus for a rule's recall patterns.

The corpus run only shows what a rule flags. This finds the places that
look like what the rule is about, so that the ones it doesn't flag can be
checked for misses. Charms are enumerated the same way as ``corpus_run.py``,
and only a charm's own source is searched: noise paths (tests, build
output, ...) and ``lib/`` (mostly vendored libraries) are skipped.

    uv run --no-project --python 3.14 --with pyyaml \\
        python -I recall_grep.py --corpus C --patterns P.txt --out hits.jsonl

``--patterns`` is a file with one Python regex per line. Output: one JSON
object per line - ``charm``, ``name``, ``path``, ``line``, ``text``,
``pattern``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from corpus_run import NOISE, charm_dirs  # ruff: ignore[E402]

SUFFIXES = {".py", ".yaml", ".yml"}
SKIP_PARTS = {"lib", "tests", "build", "parts", "stage", "prime", "node_modules"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=pathlib.Path, required=True)
    parser.add_argument("--patterns", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    patterns = []
    for line in args.patterns.read_text().splitlines():
        if not line.strip():
            continue
        try:
            patterns.append((line, re.compile(line)))
        except re.error as e:
            print(f"skipping invalid pattern {line!r}: {e}", file=sys.stderr)

    count = 0
    with args.out.open("w") as out:
        for charm, name in charm_dirs(args.corpus):
            for path in sorted(charm.rglob("*")):
                rel = path.relative_to(charm)
                if (
                    path.suffix not in SUFFIXES
                    or not path.is_file()
                    or SKIP_PARTS.intersection(rel.parts[:-1])
                    or any(part.startswith(".") for part in rel.parts)
                    or any(n in "/" + str(rel) for n in NOISE)
                ):
                    continue
                try:
                    text = path.read_text()
                except (UnicodeDecodeError, OSError):
                    continue
                for lineno, line in enumerate(text.splitlines(), 1):
                    for source, pattern in patterns:
                        if pattern.search(line):
                            out.write(
                                json.dumps({
                                    "charm": str(charm.relative_to(args.corpus)),
                                    "name": name,
                                    "path": str(rel),
                                    "line": lineno,
                                    "text": line.strip()[:200],
                                    "pattern": source,
                                })
                                + "\n"
                            )
                            count += 1
                            break
    print(f"{count} hits for {len(patterns)} patterns", file=sys.stderr)


if __name__ == "__main__":
    main()
