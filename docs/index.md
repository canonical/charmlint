---
myst:
  html_meta:
    description: charmlint is a linter for Juju charms. It checks charm source code against Canonical's charm best practices.
---

# charmlint

```{toctree}
:maxdepth: 2
:hidden: true

tutorial/index
how-to/index
reference/index
explanation/index
```

charmlint is a linter for [Juju](https://canonical.com/juju) charms. It checks charm source code against Canonical's charm best practices: observability, security, testing, metadata, configuration, and more.

charmlint is for charm authors and reviewers who want best-practice gaps caught before review rather than during it. Run it locally or in CI. It complements general-purpose tools such as ruff and pyright. A rule belongs in charmlint only if it needs knowledge of charms, Juju, or Canonical practice.

charmlint requires Python 3.12 or later. Run it from PyPI with `uvx`, with no install needed:

```text
uvx charmlint /path/to/charm
```

## In this documentation

````{domain}
```{slice} Command line
{doc}`Reference <reference/cli>` slice
```

```{slice} Rules
{doc}`All rules <reference/rules>`
{doc}`ID scheme <reference/id-scheme>`
```

```{slice} Configuration
{doc}`Reference <reference/configuration>` slice
```

```{slice} Releases
{doc}`Versioning <explanation/versioning>`
```
````

This documentation uses the [Diátaxis documentation structure](https://diataxis.fr/).

## Releases

[charmlint releases](https://github.com/canonical/charmlint/releases) are tracked on GitHub and published on [PyPI](https://pypi.org/project/charmlint/). charmlint doesn't follow semantic versioning: a minor release can add or tighten rules. See [Versioning](explanation/versioning) for details.

## Project and community

charmlint is a member of the Ubuntu family. It's an open source project ([Apache license](https://www.apache.org/licenses/LICENSE-2.0)) that warmly welcomes community contributions, suggestions, fixes and constructive feedback.

- [Report a bug](https://github.com/canonical/charmlint/issues)
- [Contribute](https://github.com/canonical/charmlint/blob/main/CONTRIBUTING.md)
- [Code of conduct](https://ubuntu.com/community/ethos/code-of-conduct)

For support, join [Charm Development](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) on Matrix. You'll be able to chat with the maintainers of charmlint (the Canonical Charm Tech team) and a friendly community of charm developers!

To follow along with updates and tips about charm development, join our [Discourse forum](https://discourse.charmhub.io/).
