.. _python_bridge:other_simulators:

Other simulators
-----------------

Riviera-PRO/Active-HDL (VHPI) implement ``python_ffi_pkg`` with a VHPI
application, built from the C sources in `src/vunit_python_bridge/native/vhpi
<https://github.com/VUnit/vunit-python-bridge/tree/main/src/vunit_python_bridge/native/vhpi>`__
with their ``ccomp`` driver. On Windows, ``ccomp`` is given the directory of
the gcc bundled with the simulator (``<installation>/mingw``) or, when there is
none, of ``gcc`` on ``PATH``. The package builds the application under the
output path (``<output path>/<simulator>/libraries``) the first time it is
added and rebuilds it when the sources, the Python running VUnit or the
simulator installation change, so a run script needs nothing beyond
``add_package("vunit-python-bridge", allow_setup=True)``.

This application differs from the Python bridge in a few ways: only the
default session exists, the operations implemented by the bridge
(``integer_array_t`` values, the ``boolean``, ``std_ulogic``, vector and
``integer_array_t`` results, ``exec_file``) report that they require NVC, GHDL
or Questa, a Python error stops the simulation with the message printed by the
application rather than through the logger of the session, and ``real`` values
outside the single precision float range are rejected.

The ``embedded_python`` example of this repository,
`examples/embedded_python
<https://github.com/VUnit/vunit-python-bridge/tree/main/examples/embedded_python>`__,
is a complete example covering all three simulator families.

Its ``tb_example.vhd`` has a test case for each part of the API: ``exec`` and
``eval`` with the types they convert, calls with positional, keyword and group
arguments, a 20 register status dump, wide
``arg_unsigned``/``arg_signed`` and ``std_ulogic`` argument values, a 2-D
``integer_array_t`` image transposed by NumPy, the result types of ``eval`` and
``call``, Python files executed with ``exec_file`` or imported with
``import_module_from_file``, two models loaded into a session each, and a
Python model failing with the logger of the default session mocked. Its last
test case drives ``python_model``, a verification component whose behaviour is
the Python function in ``python_model.py`` rather than VHDL. The component finds
that file by joining its name to ``base_path``, the directory of the run script, which
``run.py`` sets as the base directory, while the testbench gives the files it
loads itself relative to its own directory. See :ref:`python_bridge:file_paths`.
