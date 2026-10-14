Requirements
------------

* A VUnit with support for packages and simulator hooks, see the `README
  <https://github.com/VUnit/vunit-python-bridge#readme>`__.
* NVC, GHDL or Questa/ModelSim, through the VUnit Python bridge, see
  :ref:`python_bridge:native`, or Riviera-PRO/Active-HDL (VHPI) through the VHPI application, which
  the package builds in the same way, see
  :ref:`python_bridge:other_simulators`. Any other simulator raises a
  ``RuntimeError``.
* VHDL-2008 or later.
* CPython 3.10 or later with the standard (GIL) build. Free-threaded builds
  are rejected with an error.
* Linux: a C compiler (``cc``, ``gcc`` or ``clang``, or ``CC``) and
  the Python development headers (for example the ``python3-dev`` package)
  since the bridge library is compiled on first use, see
  :ref:`python_bridge:native`. Python must provide a shared ``libpython``
  (``--enable-shared``), which is the case for distribution Pythons,
  ``actions/setup-python``, ``uv`` and ``pyenv`` builds with default settings.
* Windows: a 64-bit CPython from python.org (or compatible, such as
  ``actions/setup-python`` and ``uv``). No compiler is needed for NVC and GHDL
  when the package includes the prebuilt DLLs. Otherwise, and always for
  Questa and Riviera-PRO/Active-HDL, a MinGW-w64 ``gcc`` is needed: ``CC``, the
  one bundled with the simulator if there is one, or ``gcc`` on ``PATH``.
  MSYS2/MinGW Pythons are not supported. The simulator must be a 64-bit (x64)
  build too, since the Python DLL is loaded into its process; the package
  rejects 32-bit and ARM64 simulators and Pythons.

The simulator runs Python in the same environment as VUnit itself, including
an active virtual environment and its installed packages.

A missing prerequisite, for example a missing C compiler or missing Python
headers, is reported when the package is added: ``add_package`` raises an error
explaining what to install.
