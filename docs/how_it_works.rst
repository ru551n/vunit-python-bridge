.. _python_bridge:native:

How it works (NVC, GHDL and Questa)
------------------------------------

For NVC, GHDL and Questa, the interpreter is embedded in the simulator process
by a small C library, the VUnit Python bridge (`src/vunit_python_bridge/native
<https://github.com/VUnit/vunit-python-bridge/tree/main/src/vunit_python_bridge/native>`__).
NVC and GHDL call it through VHPIDIRECT; Questa/ModelSim calls it through the
FLI, using the front end in `native/fli.c
<https://github.com/VUnit/vunit-python-bridge/blob/main/src/vunit_python_bridge/native/fli.c>`__
that converts the FLI parameters of one foreign subprogram per entry point. The generated VHDL
and everything above it is the same for all three. The interpreter is started
on first use, is never restarted within a simulation, and uses no signal
handlers of its own.

Linux
  The bridge is compiled from source against the Python running VUnit the
  first time the package is added, and cached in the library directory, see
  below. It is rebuilt automatically when the
  source, the Python version or the Python installation changes. For Questa
  the FLI front end is compiled in too, against the ``mti.h`` of the
  simulator, and the simulator installation is part of the cache key. The
  package ships no prebuilt Linux library.

Windows
  For NVC and GHDL, the package ships DLLs built with MSVC for each supported
  Python minor version (``src/vunit_python_bridge/bin``). The matching DLL is
  copied to the library directory, see below, and nothing is compiled. A development checkout of
  the package does not contain the DLLs; they can be built with
  ``tools/build_python_bridge.py`` from an MSVC developer prompt, and without
  them the library is built with gcc like for Questa. For Questa the library
  must be linked against the simulator's ``mtipli``, so it is always built on
  first use with gcc, against the headers and the import library of the
  Python running VUnit. The compiler is ``CC`` if set, else the MinGW gcc
  bundled with the simulator (``gcc-*-mingw64*`` next to the Questa
  executables' directory), else ``gcc`` on ``PATH``. Many Questa installations
  on Windows bundle none. A gcc build imports the Python DLL directly, so the
  package adds its directory to ``PATH`` for the simulator processes. These
  builds are untested.

Library directory
  The libraries are built or copied to a directory of their own rather than to the
  VUnit output path, which may not allow executing files:
  ``~/.vunit-python-bridge`` in the home directory of the user, on every
  platform (``%USERPROFILE%\.vunit-python-bridge`` on Windows). The environment
  variable ``VUNIT_PYTHON_BRIDGE_LIBRARY_DIR`` selects another directory on
  every platform. When the directory cannot be written, e.g. a read-only home
  directory in a container, the setup fails and asks for the variable to be
  set to a writable directory.
  The setup also fails, asking for the variable to be set, when the simulator
  could not load the library from the directory: on Linux and macOS when it is
  on a file system mounted ``noexec``, and on Windows when an execution policy
  (AppLocker, Windows Defender Application Control) blocks the library there.
  Any other reason the library does not load, for example a missing
  ``libpython``, fails the setup with the reason the system gives, which the
  simulators leave out. The directory can be shared by projects since every
  build has a directory named after what it was built from. The configuration
  of a project stays in ``<output path>/python_bridge`` and the simulator hooks
  pass its path to the library in ``VUNIT_PYTHON_BRIDGE_CONFIG``.

The bridge uses the full (version specific) CPython ABI rather than the
Stable ABI since embedding the interpreter in the environment VUnit runs in
requires the ``PyConfig`` initialization API, which is not part of the
limited API.

The package registers simulator hooks that make the simulator find the
library automatically. NVC is given a ``--load`` option. GHDL gets the library
directory in its dynamic library search path, plus a linker search path and an
rpath for the ahead-of-time compiled llvm and gcc backends, which the hook recognizes
from the ``backend`` of the GHDL interface it is called with.

GHDL mcode and llvm-jit find the library only through that search path
(``LD_LIBRARY_PATH``), since GHDL limits the library name in a VHPIDIRECT
attribute to 32 characters, too short for an absolute path. A ``ghdl`` wrapper
script that resets the environment, or a simulation re-run by hand outside
VUnit, then fails with ``cannot load VHPIDIRECT shared library
'libvunit_python_bridge.so'``. Such a wrapper must keep ``LD_LIBRARY_PATH``
and ``VUNIT_PYTHON_BRIDGE_CONFIG``. The llvm and gcc backends find the library
through the rpath, but they also need ``VUNIT_PYTHON_BRIDGE_CONFIG``.

The FLI
attributes generated for Questa name the library by absolute path, and the
``vsim`` process VUnit starts is given ``-noautoldlibpath`` on Linux so that
the C++ runtime Questa bundles, which is often older than the one the Python
extension modules of the environment (NumPy) were built against, does not take
precedence over the one of the system. That option is set up when the process
starts, so it has to go on the command line of the process rather than on the
``vsim`` command of the do-file VUnit generates, and it is only passed to a
``vsim`` listing it in ``vsim -help all``. No simulator options need to be set
by the user.

Tested configurations
~~~~~~~~~~~~~~~~~~~~~~

========================== ========================================================
Simulator                  Linux
========================== ========================================================
NVC                        1.22 (and 1.23-devel)
GHDL mcode                 6.0.0, 7.0.0-dev
GHDL llvm-jit              6.0.0, 7.0.0-dev
GHDL llvm                  6.0.0, 7.0.0-dev
GHDL gcc                   6.0.0, 7.0.0-dev
Questa (FLI)               Altera Starter FPGA Edition 2025.3
========================== ========================================================

On Windows, CI tests NVC 1.22 and GHDL mcode (nightly) with Python 3.10, 3.12,
3.14 and 3.15. The released wheel is also installed and tested on Linux, macOS and on
Windows machines without a compiler, there with every supported Python, so
each of its prebuilt DLLs is run.

Questa is tested manually on Linux and is not covered by CI; the Windows build
of its bridge library is untested. Riviera-PRO/Active-HDL (VHPI) is not tested
at all.
