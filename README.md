# vunit-python-bridge

[![Documentation](https://img.shields.io/readthedocs/vunit-python-bridge?label=documentation)](https://vunit-python-bridge.readthedocs.io)
[![Repository](https://img.shields.io/badge/github-VUnit%2Fvunit--python--bridge-blue?logo=github)](https://github.com/VUnit/vunit-python-bridge)
[![PyPI](https://img.shields.io/pypi/v/vunit-python-bridge?label=pip%20install%20vunit-python-bridge&color=blue)](https://pypi.org/project/vunit-python-bridge/)
[![Python versions](https://img.shields.io/badge/python-3.10%20%E2%80%93%203.15-blue?logo=python&logoColor=white)](https://vunit-python-bridge.readthedocs.io/en/latest/requirements.html)
[![License](https://img.shields.io/badge/license-MPL--2.0-blue)](https://github.com/VUnit/vunit-python-bridge/blob/main/LICENSE)
[![CI status](https://github.com/VUnit/vunit-python-bridge/actions/workflows/python_bridge.yml/badge.svg?branch=main)](https://github.com/VUnit/vunit-python-bridge/actions/workflows/python_bridge.yml)

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
vu.add_package("vunit-python-bridge", allow_setup=True)

lib = vu.add_library("lib")
lib.add_source_files("*.vhd")

vu.main()
```

`allow_setup=True` is required because, when added, the package builds its native library and
registers simulator options as part of its setup function, which VUnit only runs when the project
allows it.

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

- VUnit 5.0.0.dev12 or later (`vunit_hdl` on PyPI), which pip installs with the package.
- VHDL-2008 or later.
- CPython 3.10 or later, standard (GIL) build, with a shared `libpython` (`--enable-shared`), which
  is what distribution Pythons, `actions/setup-python`, `uv` and `pyenv` provide by default.
- Linux and macOS: a C compiler (`cc`, `gcc` or `clang`, or `CC`) and the Python development headers
  (for example the `python3-dev` package). The bridge library is compiled on first use and cached.
- Windows: a 64-bit CPython from python.org (or compatible). The package ships prebuilt DLLs
  for NVC and GHDL. Questa builds its FLI library, and NVC and GHDL their library when the DLLs
  are missing, with a MinGW-w64 gcc: `CC`, the one bundled with the simulator, or `gcc` on `PATH`.
- The bridge library is built or copied to `~/.vunit-python-bridge`, not to the VUnit
  output path. `VUNIT_PYTHON_BRIDGE_LIBRARY_DIR` selects another directory on every platform.

The simulator runs Python in the same environment as VUnit itself, including an active virtual
environment and its installed packages.

## Documentation

The documentation is at [vunit-python-bridge.readthedocs.io](https://vunit-python-bridge.readthedocs.io): sessions, `exec`, `eval`, `call`
and its argument forms, `exec_file`, `import_run_script`, the type mapping, `integer_array_t` and
NumPy, error reporting, and how the bridge works. A complete example covering all three simulator
families is in [examples/embedded_python](examples/embedded_python).

## License

Mozilla Public License, v. 2.0, like VUnit. See [LICENSE](LICENSE).
