# vunit-python-bridge

A VUnit package making Python callable from VHDL.

## Overview

vunit-python-bridge embeds a Python interpreter in the simulator process so that a VHDL testbench
can execute Python code and call Python functions — a NumPy reference model, a constraint solver, a
plot of what the design just produced — without leaving the simulation. The VHDL API,
`python_pkg`/`python_context`, is compiled into the `python_bridge` library and is implemented for
the selected simulator by a foreign language interface the package builds itself: a small C library
called through VHPIDIRECT (NVC, GHDL) or the FLI (Questa/ModelSim), or a VHPI application built with
the simulator's own compiler driver (Riviera-PRO/Active-HDL). Values cross the interface with their
VHDL types: `integer`, `real`, `string`, `boolean`, `std_ulogic`, `unsigned`/`signed`, the vector
types, and `integer_array_t` as a NumPy array.

## Installation

```bash
pip install vunit-python-bridge
```

## Basic Example

The run script adds the package after the VUnit builtins:

```python
from vunit import VUnit

vu = VUnit.from_argv()
vu.add_vhdl_builtins()
vu.add_package("vunit-python-bridge")

lib = vu.add_library("lib")
lib.add_source_files("*.vhd")

vu.main()
```

The testbench gets the API from the `python_context` context of the `python_bridge` library:

```vhdl
library vunit_lib;
context vunit_lib.vunit_context;

library python_bridge;
context python_bridge.python_context;

...

exec("import numpy as np");
exec("def gain(x): return [2 * v for v in x]");

check_equal(eval_integer("int(np.sum([1, 2, 3]))"), 6);
check_equal(eval_string("'-'.join(['a', 'b'])"), string'("a-b"));
check(call_integer_vector("gain", arg(integer_vector'(1, 2))) = integer_vector'(2, 4));
```

## Supported Simulators

| Simulator | Interface | Status |
| --- | --- | --- |
| NVC | VHPIDIRECT | Tested on Linux, macOS and Windows |
| GHDL (mcode, llvm-jit, llvm, gcc) | VHPIDIRECT | Tested on Linux, macOS and Windows |
| Questa/ModelSim | FLI | Tested manually on Linux; the Windows build is untested |
| Riviera-PRO, Active-HDL | VHPI | Untested; a subset of the API, see the documentation |

## Requirements

- `vunit_hdl >= 5.0.0.dev12`, the version carrying the support for packages and simulator hooks
  ([VUnit/vunit#1221](https://github.com/VUnit/vunit/pull/1221)). Until that is part of a release,
  install VUnit from the branch it lives on:
  `pip install git+https://github.com/ru551n/vunit.git@feature/package-setup-hooks`
- VHDL-2008 or later.
- CPython 3.10 or later, standard (GIL) build, with a shared `libpython` (`--enable-shared`), which
  is what distribution Pythons, `actions/setup-python`, `uv` and `pyenv` provide by default.
- Linux and macOS: a C compiler (`cc`, `gcc` or `clang`, or `CC`) and the Python development headers
  (for example the `python3-dev` package). The bridge library is compiled on first use and cached
  under the VUnit output path.
- Windows: nothing beyond a 64-bit CPython from python.org (or compatible). The package ships
  prebuilt DLLs for NVC and GHDL. Questa builds its FLI library with the MinGW GCC it bundles.

The simulator runs Python in the same environment as VUnit itself, including an active virtual
environment and its installed packages.

## Documentation

The user guide is in [docs/user_guide.rst](docs/user_guide.rst): sessions, `exec`, `eval`, `call`
and its argument forms, `exec_file`, `import_run_script`, the type mapping, `integer_array_t` and
NumPy, error reporting, and how the bridge works. A complete example covering all three simulator
families is in [examples/embedded_python](examples/embedded_python).

## Releasing

A release is made by tagging the commit that sets the version:

1. Bump `version` in `pyproject.toml`.
2. Commit it.
3. Tag the commit `vX.Y.Z`, with the release notes as the tag message:
   `git tag -a v0.2.0`.
4. Push the tag: `git push origin v0.2.0`.

The [release workflow](.github/workflows/release.yml) then checks that the tag names the version in
`pyproject.toml`, builds the Windows DLLs, the sdist and the wheel, runs the tests against the
installed wheel with GHDL, publishes to PyPI and creates the GitHub release with the tag message as
its body. Running the workflow manually (`workflow_dispatch`) does everything but publish and leaves
the distribution as an artifact of the run, which is how a release is rehearsed.

Publishing uses a [PyPI trusted publisher](https://docs.pypi.org/trusted-publishers/), so there is
no API token in the repository. It has to be set up once on PyPI, for project
`vunit-python-bridge`: owner `ru551n`, repository `vunit-python-bridge`, workflow `release.yml`,
environment `pypi`.

## License

Mozilla Public License, v. 2.0, like VUnit. See [LICENSE](LICENSE).
