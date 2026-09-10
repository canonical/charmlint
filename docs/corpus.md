# Measuring rules against the hyrum cache

A new or changed rule is reviewed on its true-positive / false-positive rate over the hyrum cache, not just on its unit tests. The numbers only mean something if everyone counts the same way, so count this way.

## The cache

`~/.cache/hyrum/charms/<owner>/<repo>/…`, populated by hyrum. It is a working cache, not a curated corpus: it holds build trees, vendored copies, and the same charm mirrored under more than one owner.

## Enumerating charms

A **charm** is the outermost directory holding a `charmcraft.yaml`, after dropping build and vendor noise, deduplicated by the `name` it declares. Nothing else gives a stable count.

- **Outermost.** A charm's own build tree can contain other charms (`.tox/`, test fixtures, cookiecutter templates). Counting every `charmcraft.yaml` in the cache gives ~1970 rather than ~655.
- **Excluding noise.** Skip any path containing `.tox`, `/tests/`, `/.template/`, `cookiecutter`, `/node_modules/`, `/.venv/`, `/build/`.
- **Deduplicated by name.** `git.launchpad.net/charm-kubernetes-worker` and `charmed-kubernetes/charm-kubernetes-worker` are one charm. 788 directories collapse to 655 charms.

Monorepo layouts (`repo/charms/*`, `repo/charm/`, `repo/kubernetes/`, `repo/machine/`) are each their own charm, and the outermost rule picks them up without needing to be listed.

```python
import pathlib, yaml

ROOT = pathlib.Path.home() / ".cache/hyrum/charms"
NOISE = (".tox", "/tests/", "/.template/", "cookiecutter",
         "/node_modules/", "/.venv/", "/build/")


def charm_dirs():
    """Yield one directory per distinct charm in the cache."""
    found = sorted(
        p.parent
        for p in ROOT.rglob("charmcraft.yaml")
        if not any(n in "/" + str(p.parent.relative_to(ROOT)) for n in NOISE)
    )
    outermost = [d for d in found if not any(o in d.parents for o in found)]
    seen: set[str] = set()
    for d in outermost:
        name = _declared_name(d)
        if name is None or name in seen:
            continue
        seen.add(name)
        yield d


def _declared_name(d: pathlib.Path) -> str | None:
    for filename in ("charmcraft.yaml", "metadata.yaml"):
        path = d / filename
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            return data["name"]
    return None
```

## Running the rule

```python
import sys
sys.path.insert(0, "src")
from charmlint._linter import lint

for charm in charm_dirs():
    for diag in lint(charm):
        if diag.rule_id in {"MY-001"}:
            ...  # collect charm, message, path, line
```

`lint` raises nothing for a broken charm: an unreadable file becomes a `FATAL` diagnostic in the report. Count those separately — they are neither true nor false positives, and they are usually pre-existing.

## Reporting

Two numbers matter, and they answer different questions.

- **The absolute table** — TP / FP / UNK per rule, and the FP rate. Every finding is verified against the source file by a re-parse written separately from the rule, so a bug in the rule cannot validate itself. Beware the obvious trap: `ops.interface_aws` normalises to `ops-interface-aws`, so a verifier matching on `startswith("ops")` will disagree with a correct rule.
- **The delta against the previous tip** — run the same script against the commit before the change, and diff the findings by `(charm, rule_id)`. This is what shows a guard removed exactly the false positives it was meant to and nothing else. Use `git worktree add` to get the old tree without disturbing the branch.

Quote both. An absolute table alone cannot show what a change did.
