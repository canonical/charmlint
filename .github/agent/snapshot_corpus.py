"""Freeze a slim copy of the hyrum charm cache for reproducible corpus runs.

The live cache (``~/.cache/hyrum/charms``) changes whenever hyrum refreshes,
so two backtest configurations run a week apart would be scored against
different corpora. A snapshot fixes that, and is the shape the GitHub
Actions corpus cache needs too.

Kept: every file outside the noise directories, as is if it's at most
``--max-bytes``; larger files become empty placeholders, so rules that only
check a file exists (an icon, a licence, a lock file) still see it.
Dropped: ``.git`` (left as an empty directory, as a repository-root
marker), ``.tox``, ``.venv``, ``venv``, ``node_modules``,
``__pycache__``, ``build`` and ``dist`` directories. Symlinks to files are
kept as symlinks when they point inside the cache (reactive charms link
``metadata.yaml`` to ``src/metadata.yaml``, and without the link the charm's
name can't be read), and dropped when they point outside it.

Usage::

    python3 snapshot_corpus.py --dest /w/charmlint-agent-backtest/corpus-2026-11-13
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import time

SKIP_DIRS = {
    ".git",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=pathlib.Path, default=pathlib.Path.home() / ".cache/hyrum/charms"
    )
    parser.add_argument("--dest", type=pathlib.Path, required=True)
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    args = parser.parse_args()

    if args.dest.exists():
        raise SystemExit(f"{args.dest} exists; snapshots are immutable, pick a new name")
    start = time.monotonic()
    kept = placeholders = total = links = 0
    for root, dirs, files in os.walk(args.source):
        dirs[:] = sorted(
            d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(root, d))
        )
        rel = pathlib.Path(root).relative_to(args.source)
        out_dir = args.dest / rel
        out_dir.mkdir(parents=True, exist_ok=True)
        if (pathlib.Path(root) / ".git").exists():
            # Rules find the repository root by `.git` (SUPPLYCHAIN-001's rock
            # search), so keep an empty marker where there was one.
            (out_dir / ".git").mkdir(exist_ok=True)
        for name in files:
            src = pathlib.Path(root) / name
            if not src.is_file():
                continue  # dangling link, socket, ...
            if src.is_symlink():
                target = src.resolve()
                if target.is_relative_to(args.source.resolve()):
                    (out_dir / name).symlink_to(os.readlink(src))
                    links += 1
                # A link out of the cache is dropped: copying its target would
                # copy whatever file on this machine a charm repo points at.
                continue
            size = src.stat().st_size
            if size > args.max_bytes:
                (out_dir / name).touch()
                placeholders += 1
            else:
                shutil.copy2(
                    src, out_dir / name
                )  # keeps the mode: CHARMCRAFT-003 checks the executable bit
                kept += 1
                total += size
    manifest = {
        "source": str(args.source),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files": kept,
        "placeholders": placeholders,
        "symlinks": links,
        "bytes": total,
        "max_bytes": args.max_bytes,
        "skipped_dirs": sorted(SKIP_DIRS),
    }
    (args.dest.parent / f"{args.dest.name}.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(
        f"{kept} files ({total / 1e9:.2f} GB), {placeholders} placeholders, {links} symlinks, "
        f"{time.monotonic() - start:.0f}s"
    )


if __name__ == "__main__":
    main()
