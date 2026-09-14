# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com

"""
The version of the package, as the release workflow needs it.

A release is made by tagging the commit bumping the version in pyproject.toml, so the
tag and that version must agree. Checking it here keeps a mistyped tag from reaching
PyPI, where a version cannot be taken back.

    python tools/release.py version           print the version of pyproject.toml
    python tools/release.py validate          check that the version is a release version
    python tools/release.py validate --tag v1.2.3
                                              check the tag against it as well
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent.resolve() / "pyproject.toml"

# The versions a release may have: MAJOR.MINOR.PATCH, optionally a pre-release of it.
RELEASE_VERSION = re.compile(r"\d+\.\d+\.\d+(a\d+|b\d+|rc\d+)?")


def version() -> str:
    """
    The version in pyproject.toml.
    """
    with PYPROJECT.open("rb") as fptr:
        return tomllib.load(fptr)["project"]["version"]


def validate(tag) -> None:
    """
    Fail unless the version, and the tag naming it when there is one, are what a release
    is made of.
    """
    project_version = version()
    if not RELEASE_VERSION.fullmatch(project_version):
        raise SystemExit(
            f"{PYPROJECT} has version {project_version!r}, which is not a version to release. "
            "Releases are made of MAJOR.MINOR.PATCH, optionally aN, bN or rcN."
        )

    if tag is not None and tag != f"v{project_version}":
        raise SystemExit(
            f"The tag {tag!r} does not name the version of {PYPROJECT}, which is {project_version!r}. "
            f"Expected the tag v{project_version}."
        )

    print(f"Version {project_version}" + ("" if tag is None else f", tagged {tag}"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="Print the version of pyproject.toml")
    validate_parser = commands.add_parser("validate", help="Check the version, and a tag naming it")
    validate_parser.add_argument("--tag", help="The tag the release is made from, for example v1.2.3")

    args = parser.parse_args()
    if args.command == "version":
        print(version())
    else:
        validate(args.tag)


if __name__ == "__main__":
    sys.exit(main())
