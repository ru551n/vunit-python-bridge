# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com

"""
The VHDL API reference, generated from the package declarations so that it follows the code.

A declaration is documented by the comment right above it. A comment between two lines of
dashes starts a section, titled by its first line. Names starting with p_ and sections
titled "Private" are left out.
"""

import re
from pathlib import Path

HDL = Path(__file__).parent.parent / "src" / "vunit_python_bridge" / "hdl" / "src"

# The documented packages: name, file, introduction
PACKAGES = [
    (
        "python_ffi_pkg",
        "python_ffi_pkg_bridge.vhd",
        "Sessions, ``exec`` and the basic ``eval`` result types. The package is implemented for "
        "the selected simulator: by the Python bridge for NVC, GHDL and Questa and by a VHPI "
        "application for Riviera-PRO/Active-HDL, which declares the same API, see "
        ":doc:`../other_simulators`.",
    ),
    (
        "python_pkg",
        "python_pkg.vhd",
        "Arguments, ``call``, the result types implemented by the Python bridge, Python files "
        "and modules, and ``base_path``.",
    ),
]

BANNER = re.compile(r"^\s*-{10,}\s*$")
PRIVATE_DECLARATION = re.compile(r"^\s*(constant|signal|variable|type|subtype|alias)\s+p_\w+")
DECLARED_NAME = re.compile(
    r'^\s*(?:impure\s+|pure\s+)?(?:function|procedure|type|subtype|constant|alias)\s+("[^"]+"|\w+)'
)
PRIVATE_SUBPROGRAM = re.compile(r"^\s*(impure\s+|pure\s+)?(function|procedure)\s+p_\w+")


def _declarations(path, package):
    """
    The comment and code chunks of the package declaration, separated by blank lines.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(idx for idx, line in enumerate(lines) if re.match(rf"package {package} is\b", line))
    end = next(idx for idx in range(start, len(lines)) if re.match(r"end package", lines[idx]))
    chunks, chunk = [], []
    for line in lines[start + 1 : end]:
        if line.strip():
            chunk.append(line[2:] if line.startswith("  ") else line)
        elif chunk:
            chunks.append(chunk)
            chunk = []
    return chunks + [chunk] if chunk else chunks


def _comment_text(lines):
    """
    Comment lines as reStructuredText, an indented comment line being a code example.
    """
    out, in_code = [], False
    for line in lines:
        text = line.strip()[2:]
        text = text[1:] if text.startswith(" ") else text
        code = text.startswith("  ")
        if code and not in_code:
            out += ["", ".. code-block:: vhdl", ""]
        elif not code and in_code:
            out.append("")
        in_code = code
        out.append(f"    {text}" if code else re.sub(r"([\\*`|_])", r"\\\1", text))
    return out + [""]


def _public_code(code):
    """
    The code of a chunk without its private declarations, which end at the first ; outside
    parentheses.
    """
    out, skipping, depth = [], False, 0
    for line in code:
        skipping = skipping or bool(PRIVATE_DECLARATION.match(line) or PRIVATE_SUBPROGRAM.match(line))
        if not skipping:
            out.append(line)
            continue
        depth += line.count("(") - line.count(")")
        skipping = not (depth == 0 and line.rstrip().endswith(";"))
    return out


def package_page(package, file_name, introduction):
    """
    The reference page of a package.
    """
    body, names, private = [], {}, False
    for chunk in _declarations(HDL / file_name, package):
        comment = [line for line in chunk if line.lstrip().startswith("--")]
        code = [line for line in chunk if not line.lstrip().startswith("--")]
        if BANNER.match(chunk[0]):
            banners = [idx for idx, line in enumerate(chunk) if BANNER.match(line)]
            heading = chunk[banners[0] + 1].strip()[2:].strip()
            private = heading.startswith("Private")
            if private:
                continue
            body += [heading, "-" * len(heading), ""]
            comment = [line for line in chunk[banners[1] + 1 :] if line.lstrip().startswith("--")]
        if private:
            continue
        code = _public_code(code)
        # A target for the first declaration of every name, which the contents link to
        for line in code:
            match = DECLARED_NAME.match(line)
            if match and match.group(1) not in names:
                names[match.group(1)] = f"{package}-{len(names)}"
                body += [f".. _{names[match.group(1)]}:", ""]
        if comment:
            body += _comment_text(comment)
        if code:
            body += [".. code-block:: vhdl", ""] + [f"    {line}" for line in code] + [""]
    contents = " · ".join(f":ref:`{name} <{label}>`" for name, label in sorted(names.items()))
    title = package
    out = [title, "=" * len(title), "", introduction, "", f"Declared in ``{file_name}``.", ""]
    return "\n".join(out + ["**Contents:** " + contents.replace("*", "\\*"), ""] + body)


def context_page():
    """
    The reference page of python_context.
    """
    text = (HDL / "python_context.vhd").read_text(encoding="utf-8")
    context = text[text.index("context python_context") :].strip()
    packages = ", ".join(f":doc:`{package}`" for package, _, _ in PACKAGES)
    out = ["python_context", "==============", ""]
    out += [f"The context that makes the whole API visible: {packages}.", ""]
    out += [".. code-block:: vhdl", ""] + [f"    {line}" for line in context.splitlines()] + [""]
    out += ["A testbench uses it next to ``vunit_context``:", "", ".. code-block:: vhdl", ""]
    out += ["    library vunit_lib;", "    context vunit_lib.vunit_context;", ""]
    out += ["    library python_bridge;", "    context python_bridge.python_context;", ""]
    return "\n".join(out)


def write(directory):
    """
    Write the reference pages to directory.
    """
    directory.mkdir(exist_ok=True)
    (directory / "python_context.rst").write_text(context_page(), encoding="utf-8")
    for package, file_name, introduction in PACKAGES:
        (directory / f"{package}.rst").write_text(package_page(package, file_name, introduction), encoding="utf-8")
