# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com

"""
Sphinx configuration of the vunit-python-bridge documentation.

Build with: sphinx-build -b html docs docs/_build
"""

project = "vunit-python-bridge"
copyright = "2014-2026, Lars Asplund"  # pylint: disable=redefined-builtin
author = "Lars Asplund"
release = "0.1.0"

extensions = []
exclude_patterns = ["_build"]
html_theme = "alabaster"
