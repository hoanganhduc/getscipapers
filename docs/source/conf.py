"""Sphinx configuration for the getscipapers project."""

from __future__ import annotations

import os
import sys
from datetime import datetime

# Add project root to sys.path so autodoc can import modules
sys.path.insert(0, os.path.abspath("../.."))

project = "getscipapers"
author = "Duc A. Hoang"
current_year = datetime.now().year
current_date = datetime.now().strftime("%Y-%m-%d")
copyright = f"2023-{current_year}, {author}"
release = "0.1.4"
version = release

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinx_autodoc_typehints",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "linkify",
    "substitution",
    "attrs",
]

templates_path = ["_templates"]
exclude_patterns: list[str] = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
rst_epilog = f".. |last_updated| replace:: {current_date}"

# Mock heavy dependencies so autodoc can run in lightweight environments
autodoc_mock_imports = [
    "selenium",
    "telethon",
    "libstc_geck",
    "unpywall",
    "pandas",
    "numpy",
    "PyPDF2",
    "fitz",
    "PyMuPDF",
    "pikepdf",
    "pysocks",
]

autodoc_typehints = "description"
autodoc_member_order = "bysource"
