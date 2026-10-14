# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com

"""
Sphinx configuration of the vunit-python-bridge documentation.

Build with: sphinx-build -b html docs docs/_build
"""

import sys
import tomllib
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "docs"))

project = "vunit-python-bridge"
copyright = "2014-2026, Lars Asplund"  # pylint: disable=redefined-builtin
author = "Lars Asplund"
with (ROOT / "pyproject.toml").open("rb") as fptr:
    release = tomllib.load(fptr)["project"]["version"]

extensions = ["myst_parser"]
# The release notes start at ## since they are included under a version heading
suppress_warnings = ["myst.header"]
exclude_patterns = ["_build"]

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "prev_next_buttons_location": "both",
    "navigation_depth": 3,
}
# The "Edit on GitHub" link of every page
html_context = {
    "display_github": True,
    "github_user": "VUnit",
    "github_repo": "vunit-python-bridge",
    "github_version": "main",
    "conf_py_path": "/docs/",
}


# The release notes page, generated from release_notes/*.md, newest first
_notes = ["Release notes", "=============", ""]
for _path in sorted((ROOT / "release_notes").glob("*.md"), key=lambda path: Version(path.stem), reverse=True):
    _title = _path.stem if Version(_path.stem) <= Version(release) else f"{_path.stem} (unreleased)"
    _notes += [_title, "-" * len(_title), "", f".. include:: ../release_notes/{_path.name}"]
    _notes += ["   :parser: myst_parser.sphinx_", ""]
(ROOT / "docs" / "release_notes.rst").write_text("\n".join(_notes))
