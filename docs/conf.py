import datetime
import os
import pathlib
import sys
import textwrap
from typing import Any

# [BEYOND SPHINX STACK] Make charmlint importable, so that sphinxcontrib-autoprogram can
# build the CLI reference from the real argument parser.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

# Configuration for the Sphinx documentation builder.
# All configuration specific to your project should be done in this file.
#
# If you're new to Sphinx and don't want any advanced or custom features,
# just go through the items marked 'TODO'.
#
# A complete list of built-in Sphinx configuration values:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
#
# The Sphinx Stack uses the Ulwazi theme:
# https://github.com/canonical/ulwazi

#######################
# Project information #
#######################

# Project name
project = "charmlint documentation"

# Author name; used in the default copyright statement in the page footer
author = "Canonical Ltd."

# The year in the copyright statement
copyright = f"{datetime.date.today().year}"

# String appended to the title of individual HTML pages
html_title = project

# Documentation website URL
# [BEYOND SPHINX STACK] The final URL isn't confirmed yet. This follows the pattern of the
# other Charm Tech docs, such as https://canonical.com/juju/docs/jubilant/.
ogp_site_url = "https://canonical.com/juju/docs/charmlint/"

# Preview name of the documentation website
ogp_site_name = project

# Preview image URL
ogp_image = "https://assets.ubuntu.com/v1/cc828679-docs_illustration.svg"

# Product favicon; shown in bookmarks, browser tabs, etc.
# TODO: To customise the favicon, uncomment and update the next line.
# html_favicon = "_static/favicon.png"

# The theme for the HTML output
html_theme = "ulwazi"

# Dictionary of values to pass into every page's template.
html_context = {
    # Community links for the 'Resources' dropdown menu.
    "discourse": "https://discourse.charmhub.io",
    "mattermost": "",
    "matrix": "https://matrix.to/#/#charmhub-charmdev:ubuntu.com",
    "github_url": "https://github.com/canonical/charmlint",
    # Feedback and edit/view links require a valid `github_url`.
    "feedback": True,
    # Brand configuration for the leftmost entry in the banner
    # [BEYOND SPHINX STACK] charmlint is part of the Juju ecosystem, so the banner links
    # to the Juju product page and uses the Juju tag image, like the other Charm Tech docs.
    # The image is a local file, so setup() below makes its path relative to each page.
    "logo_title": "Juju",
    "logo_link_URL": "https://canonical.com/juju",
    "logo_img_URL": "_static/logos/juju-logo-no-text.png",
    # License information to be rendered in the footer
    "author": author,
    "license": {
        "name": "Apache-2.0",
        "url": "https://github.com/canonical/charmlint/blob/main/LICENSE",
    },
}

#######################
# Sitemap configuration: https://sphinx-sitemap.readthedocs.io/
#######################

# Use RTD canonical URL to ensure duplicate pages have a specific canonical URL
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "/")

# [BEYOND SPHINX STACK] Name the sitemap like the other Charm Tech docs, which are served
# under canonical.com alongside other documentation sets.
sitemap_filename = "doc-sitemap.xml"

# sphinx-sitemap uses html_baseurl to generate the full URL for each page:
sitemap_url_scheme = "{link}"

# Include `lastmod` dates in the sitemap:
sitemap_show_lastmod = True

# Pages excluded from the sitemap:
sitemap_excludes = [
    "404/",
    "genindex/",
    "search/",
]

################################
# Template and asset locations #
################################

html_static_path = ["_static"]

#############
# Redirects #
#############

# Add redirects to the 'redirects.txt' file
# https://sphinxext-rediraffe.readthedocs.io/en/latest/

# To set up redirects in the Read the Docs project dashboard:
# https://docs.readthedocs.io/en/stable/guides/redirects.html

rediraffe_redirects = "redirects.txt"

# Strips '/index.html' from destination URLs when building with 'dirhtml'
rediraffe_dir_only = True


############################
# sphinx-llm configuration #
############################

# This description is included in llms.txt to provide some initial context for your
# product docs.
llms_txt_description = textwrap.dedent(
    """\
    This is the documentation for charmlint, a linter for Juju charms that checks charm
    source code against Canonical's charm best practices.
    """
)

# Generate an 'llms-full.txt' file containing all of the documentation content
llms_txt_full_build = True

# [BEYOND SPHINX STACK] The Markdown sub-build for llms.txt has no writer for the page
# descriptions in each page's front matter, and warns about each one. The descriptions
# are HTML metadata, so drop them from the Markdown output quietly. Otherwise the warnings
# fail the HTML build, which treats warnings as errors.
llms_txt_suppress_unknown_node_warnings = ["meta"]

# The base URL for references built by sphinx-markdown-builder.
if os.environ.get("READTHEDOCS"):
    markdown_http_base = html_baseurl

###########################
# Link checker exceptions #
###########################

# A regex list of URLs that are ignored by 'make linkcheck'
linkcheck_ignore = [
    "http://127.0.0.1:8000",
    "https://github.com",
    r"https://matrix\.to/.*",
    "https://example.com",
    # SourceForge domains often block linkcheck
    r"https://.*\.sourceforge\.(net|io)/.*",
]

# A regex list of URLs where anchors are ignored by 'make linkcheck'
linkcheck_anchors_ignore_for_url = [r"https://github\.com/.*"]

# How long the link checker will wait for a response for each request
# TODO: Decrease to improve run time or increase if links frequently time out.
# linkcheck_timeout = 30

# Give linkcheck multiple tries on failure
linkcheck_retries = 3

########################
# Configuration extras #
########################

# Custom Sphinx extensions; see
# https://www.sphinx-doc.org/en/master/usage/extensions/index.html
extensions = [
    "ulwazi",
    "myst_parser",
    "sphinx_design",
    "sphinx_rerediraffe",
    "sphinxcontrib.jquery",
    "sphinxext.opengraph",
    "sphinx_config_options",
    "sphinx_llm.txt",
    "sphinx_modern_pdf_style",
    "sphinx_related_links",
    "sphinx_roles",
    "sphinx_terminal",
    "sphinx_youtube_links",
    "sphinxcontrib.cairosvgconverter",
    "sphinx.ext.intersphinx",
    "sphinx_sitemap",
    # [BEYOND SPHINX STACK] Build the CLI reference from charmlint's argument parser.
    "sphinxcontrib.autoprogram",
]

# Excludes files or directories from processing
exclude_patterns = [
    "doc-cheat-sheet*",
    ".venv*",
    "_dev",
    # [BEYOND SPHINX STACK] Contributor-only notes, kept in docs/ so links to them still
    # work, but not part of the published site.
    "corpus.md",
]

# Adds custom CSS files, located remotely or in 'html_static_path'.
html_css_files = [
    "https://assets.ubuntu.com/v1/d86746ef-cookie_banner.css",
]

# Adds custom JavaScript files, located remotely or in 'html_static_path'.
html_js_files = [
    "https://assets.ubuntu.com/v1/287a5e8f-bundle.js",
    # [BEYOND SPHINX STACK] Rewrite the Read the Docs version switcher links.
    "overwrite_links.js",
]

# Appends extra markup to the end of every document written in reST
# rst_epilog = """
# """

# Project slug
slug = "juju/docs/charmlint"

# Apply modern PDF styling and configuration
set_modern_pdf_config = True

# Your manpage URL
# TODO: To enable manpage links, uncomment and replace {codename} with required
#       release, preferably an LTS release (e.g. noble). Do *not* substitute
#       {section} or {page}; these will be replaced by sphinx at build time
#
# If set, the :manpage: role creates an inline link to the manual page.
# manpages_url = 'https://manpages.ubuntu.com/manpages/{codename}/en/' + \
#     'man{section}/{page}.{section}.html'

# Specifies a reST snippet to be prepended to each .rst file
# This defines a :center: role that centers table cell content.
rst_prolog = """
.. role:: center
   :class: align-center
.. role:: h2
    :class: hclass2
.. role:: woke-ignore
    :class: woke-ignore
.. role:: vale-ignore
    :class: vale-ignore
"""

# Configuration for Intersphinx projects
#
# intersphinx_mapping = {
#     "snap": ("https://snapcraft.io/docs/", None),
# }


# [BEYOND SPHINX STACK]
# The following project-specific config goes beyond the provisions of Sphinx Stack.

# Generate anchors for headings down to level 3, so that the links in the generated rule
# reference (such as #security-001-secret-in-plain-config) resolve. The existing pages
# are also read on GitHub, which generates the same slugs.
myst_heading_anchors = 3


def _set_logo_path(
    app: object, pagename: str, templatename: str, context: dict, doctree: object
) -> None:
    """Make the banner's logo path relative to the page being written.

    Ulwazi uses ``logo_img_URL`` as it is, so a path into ``_static`` only works on the
    home page unless it is resolved for each page.
    """
    del app, pagename, templatename, doctree
    logo = context.get("logo_img_URL", "")
    if logo and "://" not in logo:
        context["logo_img_URL"] = context["pathto"](logo, 1)


def setup(app: Any) -> None:  # Any, as Sphinx is only installed in the docs venv.
    app.connect("html-page-context", _set_logo_path)
