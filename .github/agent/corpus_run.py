"""Run one charmlint checkout over the hyrum corpus and write every finding.

Charms are enumerated exactly as charmlint's ``docs/corpus.md`` describes:
the outermost directory holding a ``charmcraft.yaml``, noise paths skipped,
deduplicated by declared name.

All rules run, not only the changed ones, so the scorer can see both the
rule under test and any accidental change to another rule.

Run it with the checkout's own code and PyYAML, isolated from this
directory::

    uv run --no-project --python 3.14 --with pyyaml \\
        python -I corpus_run.py --checkout REPO --out findings.jsonl

Output: one JSON object per line - ``charm``, ``name``, ``rule_id``,
``severity``, ``path``, ``line``, ``message``. A summary line goes to stderr.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import pathlib
import sys
import time
from collections.abc import Iterator

import yaml

# Exactly as docs/corpus.md, so the denominator matches the PR tables.
NOISE = (".tox", "/tests/", "/.template/", "cookiecutter", "/node_modules/", "/.venv/", "/build/")
DEFAULT_CORPUS = pathlib.Path.home() / ".cache/hyrum/charms"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=pathlib.Path, required=True)
    parser.add_argument("--corpus", type=pathlib.Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--jobs", type=int, default=os.cpu_count())
    parser.add_argument("--limit", type=int, help="only the first N charms (for smoke tests)")
    parser.add_argument(
        "--min-charms",
        type=int,
        default=500,
        help="fail if the corpus has fewer charms than this (a missing or partial cache)",
    )
    args = parser.parse_args()

    charms = list(charm_dirs(args.corpus)) if args.corpus.is_dir() else []
    if len(charms) < args.min_charms and not args.limit:
        raise SystemExit(
            f"{args.corpus}: {len(charms)} charms, expected at least {args.min_charms}"
        )
    if args.limit:
        charms = charms[: args.limit]

    start = time.monotonic()
    initargs = (str(args.checkout.resolve() / "src"),)
    with multiprocessing.Pool(args.jobs, initializer=_init, initargs=initargs) as pool:
        results = pool.map(
            _lint_one, [(str(c), str(args.corpus), n) for c, n in charms], chunksize=4
        )

    fatal = 0
    count = 0
    with args.out.open("w") as f:
        for findings in results:
            for finding in findings:
                fatal += finding["rule_id"] == "FATAL"
                count += 1
                f.write(json.dumps(finding, sort_keys=True) + "\n")
    elapsed = time.monotonic() - start
    summary = {"charms": len(charms), "findings": count, "fatal": fatal, "seconds": round(elapsed)}
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary) + "\n")
    print(
        f"{len(charms)} charms, {count} findings ({fatal} FATAL) in {elapsed:.0f}s",
        file=sys.stderr,
    )


def charm_dirs(root: pathlib.Path) -> Iterator[tuple[pathlib.Path, str]]:
    """Yield ``(directory, declared name)`` for each distinct charm."""
    found = sorted(
        p.parent
        for p in root.rglob("charmcraft.yaml")
        if not any(n in "/" + str(p.parent.relative_to(root)) for n in NOISE)
    )
    found_set = set(found)
    outermost = [d for d in found if not any(parent in found_set for parent in d.parents)]
    seen: set[str] = set()
    for d in outermost:
        name = _declared_name(d)
        if name is None or name in seen:
            continue
        seen.add(name)
        yield d, name


def _declared_name(d: pathlib.Path) -> str | None:
    for filename in ("charmcraft.yaml", "metadata.yaml"):
        path = d / filename
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            return data["name"]
    return None


_lint = None


def _init(src: str) -> None:
    global _lint
    sys.path.insert(0, src)
    from charmlint._linter import lint  # ruff: ignore[PLC0415] - imported from the checkout under test

    _lint = lint


def _lint_one(item: tuple[str, str, str]) -> list[dict]:
    charm, root, name = item
    rel = str(pathlib.Path(charm).relative_to(root))
    if _lint is None:
        raise RuntimeError("worker not initialised")
    try:
        diagnostics = list(_lint(pathlib.Path(charm)))
    except Exception as e:  # ruff: ignore[BLE001] - a crash is a finding for the scorer, not a harness failure
        return [_record(rel, name, "CRASH", "error", None, None, f"{type(e).__name__}: {e}")]
    return [
        _record(
            rel,
            name,
            d.rule_id,
            getattr(d.severity, "value", str(d.severity)),
            d.path,
            d.line,
            d.message,
        )
        for d in diagnostics
    ]


def _record(
    charm: str,
    name: str,
    rule_id: str,
    severity: str,
    path: str | None,
    line: int | None,
    message: str,
) -> dict:
    return {
        "charm": charm,
        "name": name,
        "rule_id": rule_id,
        "severity": severity,
        "path": str(path) if path is not None else None,
        "line": line,
        "message": message,
    }


if __name__ == "__main__":
    main()
