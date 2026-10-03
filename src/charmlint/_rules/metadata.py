"""Metadata rules — charmcraft.yaml / metadata.yaml field completeness.

Each rule checks the key spelling that belongs in the file the charm
actually uses: modern charmcraft.yaml uses `title` and `links.*`; legacy
metadata.yaml uses `display-name`, `docs`, `issues`, `source` at top
level. Accepting the wrong spelling in the wrong file would silently
paper over a real misplacement.

A charm with both files uses metadata.yaml, which charmcraft packs as it
is, so that is the file whose spelling counts.
"""

import urllib.parse

from .. import _models as models
from ._base import Rule


def _resolve(metadata: models.Yaml, dotted: str) -> models.Yaml:
    """Follow a dotted path through nested mappings, e.g. ``links.issues``."""
    node = metadata
    for part in dotted.split("."):
        node = node.get(part)
    return node


def _is_own_charmhub_page(url: str, name: str) -> bool:
    """Report whether *url* is the Charmhub landing page for charm *name*."""
    candidate = url.strip()
    # A scheme-less `charmhub.io/foo` parses as a bare path, so give it one.
    if "://" not in candidate:
        candidate = f"//{candidate}"
    try:
        parts = urllib.parse.urlsplit(candidate)
    except ValueError:
        return False
    if parts.scheme not in ("", "http", "https"):
        return False
    if parts.hostname is None or parts.hostname.lower().removeprefix("www.") != "charmhub.io":
        return False
    return [segment for segment in parts.path.split("/") if segment] == [name]


def _is_charmcraft(context: models.CharmContext) -> bool:
    return _metadata_file(context) == "charmcraft.yaml"


def _metadata_file(context: models.CharmContext) -> str:
    """Return the file whose spellings the charm's metadata uses.

    That is metadata.yaml whenever the charm has one, even alongside a
    charmcraft.yaml: charmcraft packs a split charm's metadata.yaml as it
    is, so ``title`` or ``links`` written in charmcraft.yaml never reach
    the charm. ``context.metadata.source`` can't answer this, because the
    merged metadata takes its source from charmcraft.yaml whenever that
    file exists.
    """
    if any(node.source == "metadata.yaml" for _, node in context.metadata.items()):
        return "metadata.yaml"
    return context.metadata.source


def _is_bundle(context: models.CharmContext) -> bool:
    # Bundles declare `type: bundle` in charmcraft.yaml, or use the legacy
    # top-level bundle.yaml layout. Neither shape needs the charm-metadata
    # fields these rules check for.
    if context.metadata.get("type").value == "bundle":
        return True
    return (context.charm_dir / "bundle.yaml").is_file()


class MissingName(Rule):
    """Check that the charm declares a ``name``.

    ``name`` is the charm's identity: what it is published under on
    Charmhub, and what ``juju deploy`` is given. charmcraft refuses to
    pack a charm without one, so the charm is not merely untidy, it
    does not build.

    An empty value counts as missing — ``name:`` with nothing after it
    names nothing. Bundles are skipped, here and in the rest of this
    family: these are charm-metadata fields, and a bundle declares none
    of them.
    """

    category = "METADATA"
    number = 1
    name = "missing-name"
    description = "Empty or missing 'name' field in charm metadata"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-name"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        if _resolve(context.metadata, "name"):
            return []
        return [self.diagnostic(self.description, path=context.metadata.source)]


class MissingDisplayName(Rule):
    """Check that the charm declares a human-readable title.

    The title is the name Charmhub shows for the charm, where ``name``
    is the identifier it is deployed by. Juju never needs it, so a
    charm without one still works — it just appears under its
    package-style name wherever a person is reading.

    The key is ``title`` in charmcraft.yaml and ``display-name`` in
    metadata.yaml, and only the spelling belonging to the file the
    charm uses counts: writing ``display-name`` in charmcraft.yaml is a
    misplacement rather than a title.

    A charm with both files uses metadata.yaml's spelling, and is told
    about metadata.yaml: charmcraft packs that file as it is, so a
    ``title`` in charmcraft.yaml never reaches the charm.
    """

    category = "METADATA"
    number = 2
    name = "missing-display-name"
    description = "Empty or missing 'display-name'/'title' field"
    default_severity = models.Severity.WARNING
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-title"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "title" if _is_charmcraft(context) else "display-name"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' field", path=_metadata_file(context))]


class MissingSummary(Rule):
    """Check that the charm declares a ``summary``.

    The summary is the one-line description that identifies the charm
    in ``juju info``, in ``charmhub`` search results, and anywhere else
    charms are listed rather than read about. charmcraft requires it to
    pack.
    """

    category = "METADATA"
    number = 3
    name = "missing-summary"
    description = "Empty or missing 'summary' field"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-summary"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        if _resolve(context.metadata, "summary"):
            return []
        return [self.diagnostic(self.description, path=context.metadata.source)]


class MissingDescription(Rule):
    """Check that the charm declares a ``description``.

    The description is the prose Charmhub shows on the charm's page:
    what the charm deploys, and what someone is choosing when they
    choose it. charmcraft requires it to pack.

    Only presence is checked. Whether the description is worth reading
    is not something a linter can tell, so a one-word description
    satisfies this rule.
    """

    category = "METADATA"
    number = 4
    name = "missing-description"
    description = "Empty or missing 'description' field"
    default_severity = models.Severity.ERROR
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-description"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        if _resolve(context.metadata, "description"):
            return []
        return [self.diagnostic(self.description, path=context.metadata.source)]


class MissingDocs(Rule):
    """Check that the charm links to its documentation.

    Without the link, a reader who finds the charm on Charmhub has
    nowhere to go for how to operate it. Advisory, because a charm
    deploys perfectly well without it.

    The key is ``links.documentation`` in charmcraft.yaml and ``docs``
    at the top level in metadata.yaml, and only the spelling belonging
    to the file the charm uses counts (metadata.yaml, for a charm that has
    both).
    """

    category = "METADATA"
    number = 5
    name = "missing-docs"
    description = "Empty or missing 'docs' URL"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "links.documentation" if _is_charmcraft(context) else "docs"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' URL", path=_metadata_file(context))]


class MissingIssues(Rule):
    """Check that the charm links to its issue tracker.

    The link is how someone who hits a bug in the charm reports it
    rather than working around it. Advisory, because a charm deploys
    perfectly well without it.

    The key is ``links.issues`` in charmcraft.yaml and ``issues`` at
    the top level in metadata.yaml, and only the spelling belonging to
    the file the charm uses counts (metadata.yaml, for a charm that has
    both).
    """

    category = "METADATA"
    number = 6
    name = "missing-issues"
    description = "Empty or missing 'issues' URL"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links-issues"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "links.issues" if _is_charmcraft(context) else "issues"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' URL", path=_metadata_file(context))]


class MissingSource(Rule):
    """Check that the charm links to its source.

    The link is how someone reading the charm on Charmhub finds the
    code behind it — to see what it actually does, or to fix it.
    Advisory, because a charm deploys perfectly well without it.

    The key is ``links.source`` in charmcraft.yaml and ``source`` at
    the top level in metadata.yaml, and only the spelling belonging to
    the file the charm uses counts (metadata.yaml, for a charm that has
    both).
    """

    category = "METADATA"
    number = 7
    name = "missing-source"
    description = "Empty or missing 'source' URL"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links-source"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        key = "links.source" if _is_charmcraft(context) else "source"
        if _resolve(context.metadata, key):
            return []
        return [self.diagnostic(f"Empty or missing '{key}' URL", path=_metadata_file(context))]


def _missing_optional_diagnostics(
    rule: Rule,
    endpoints: models.Yaml,
    section: str,
) -> list[models.Diagnostic]:
    """Return one diagnostic per endpoint in ``section`` lacking ``optional``."""
    diagnostics: list[models.Diagnostic] = []
    for name, definition in endpoints.items():
        # Only a mapping can declare `optional`; a malformed entry is not
        # this rule's finding to report.
        if not isinstance(definition.value, dict):
            continue
        if "optional" in definition:
            continue
        diagnostics.append(
            rule.diagnostic(
                f"{section} endpoint `{name}` does not declare `optional` — "
                "charm authors should explicitly state whether the relation is "
                "required for the charm to function",
                path=definition.source,
                fix_hint=(
                    f"Add `optional: true` or `optional: false` to the `{name}` "
                    f"entry under `{section}`"
                ),
            )
        )
    return diagnostics


class RequiresMissingOptional(Rule):
    """Flag ``requires`` endpoints that don't explicitly declare ``optional``."""

    category = "METADATA"
    number = 8
    name = "requires-missing-optional"
    description = "requires endpoint missing explicit `optional` field"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#endpoint-role-endpoint-name-optional"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _missing_optional_diagnostics(self, context.metadata.get("requires"), "requires")


class ProvidesMissingOptional(Rule):
    """Flag ``provides`` endpoints that don't explicitly declare ``optional``."""

    category = "METADATA"
    number = 9
    name = "provides-missing-optional"
    description = "provides endpoint missing explicit `optional` field"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#endpoint-role-endpoint-name-optional"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        return _missing_optional_diagnostics(self, context.metadata.get("provides"), "provides")


class CircularWebsiteLink(Rule):
    """Flag a `website` link that points at the charm's own Charmhub page.

    The Charmhub page is where users land from `juju info` and Charmhub
    search, so a `website` field pointing back at it renders a link from
    the page to itself. Sub-pages (`/<charm>/docs`, `/<charm>/configure`)
    are left alone: those carry content the top-level page does not, so
    they are a deliberate destination rather than a circular link.
    """

    category = "METADATA"
    number = 10
    name = "circular-website-link"
    description = "'website' link points to the charm's own Charmhub page"
    default_severity = models.Severity.INFO
    reference_url = "https://canonical.com/juju/docs/charmcraft/stable/reference/files/charmcraft-yaml-file/#charmcraft-yaml-key-links"

    def check(self, context: models.CharmContext) -> list[models.Diagnostic]:
        if _is_bundle(context):
            return []
        name = context.metadata.get("name").value
        if not isinstance(name, str) or not name:
            return []
        diagnostics: list[models.Diagnostic] = []
        for top_level_key, key, spelt_in in (
            ("links", "links.website", "charmcraft.yaml"),
            ("website", "website", "metadata.yaml"),
        ):
            field = context.metadata.get(top_level_key)
            if not field.present:
                continue
            # A charm may split its metadata across both files, so each
            # spelling is judged against the file its key came from: the same
            # key in the other file is a misplaced field rather than a link.
            if field.source != spelt_in:
                continue
            node = _resolve(context.metadata, key)
            # Both files accept a single URL or a list of them. A listed URL
            # carries its own line, so the finding points at the offending
            # entry rather than at the key above it.
            for link in node.elements if node.elements is not None else [node]:
                url = link.value
                if not isinstance(url, str) or not _is_own_charmhub_page(url, name):
                    continue
                diagnostics.append(
                    self.diagnostic(
                        f"'{key}' points to the charm's own Charmhub page ({url})",
                        path=link.source,
                        line=link.line,
                        fix_hint="Link to the project's own site, or omit 'website'",
                    )
                )
        return diagnostics
