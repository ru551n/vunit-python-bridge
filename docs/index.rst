.. _python_bridge:

About vunit-python-bridge
=========================

|docs| |repository| |pypi| |python| |license| |ci|

.. |docs| image:: https://img.shields.io/readthedocs/vunit-python-bridge?label=documentation
   :alt: Documentation
   :target: https://vunit-python-bridge.readthedocs.io
.. |repository| image:: https://img.shields.io/badge/github-VUnit%2Fvunit--python--bridge-blue?logo=github
   :alt: Repository
   :target: https://github.com/VUnit/vunit-python-bridge
.. |pypi| image:: https://img.shields.io/pypi/v/vunit-python-bridge?label=pip%20install%20vunit-python-bridge&color=blue
   :alt: PyPI
   :target: https://pypi.org/project/vunit-python-bridge/
.. |python| image:: https://img.shields.io/badge/python-3.10%20%E2%80%93%203.15-blue?logo=python&logoColor=white
   :alt: Python versions
   :target: requirements.html
.. |license| image:: https://img.shields.io/badge/license-MPL--2.0-blue
   :alt: License
   :target: https://github.com/VUnit/vunit-python-bridge/blob/main/LICENSE
.. |ci| image:: https://github.com/VUnit/vunit-python-bridge/actions/workflows/python_bridge.yml/badge.svg?branch=main
   :alt: CI status
   :target: https://github.com/VUnit/vunit-python-bridge/actions/workflows/python_bridge.yml

vunit-python-bridge is a `VUnit <https://vunit.github.io>`__ package that embeds a Python
interpreter in the simulator, so that a VHDL testbench can execute Python code and call Python
functions -- a NumPy reference model, a constraint solver, a plot of what the design just
produced -- without leaving the simulation.

Key features
------------

* :doc:`Run Python code <running_code>` with ``exec``, evaluate expressions with ``eval`` and
  call functions with ``call``, with the result converted to the VHDL type the context expects.
* :doc:`Values cross with their VHDL types <types>`: ``integer``, ``real``, ``string``,
  ``boolean``, ``std_ulogic``, ``unsigned``/``signed``, the vector types, and ``integer_array_t``
  as a NumPy array.
* :doc:`Sessions <sessions>` give models and component instances Python namespaces of their own.
* :doc:`Python files and modules <python_files>`, including the run script itself, are executed or
  imported from VHDL, with :doc:`file paths <file_paths>` that work for testbenches and
  verification components alike.
* :doc:`Python errors <errors>` are VUnit failures with the traceback, on a logger that a test can
  mock.
* A complete :doc:`VHDL API reference <api/python_context>`, generated from the package
  declarations.
* No build step: the package builds the foreign language interface for the simulator itself, see
  :doc:`how_it_works`.

Supported simulators
--------------------

=================================  ==========  ========================================================
Simulator                          Interface   Status
=================================  ==========  ========================================================
NVC                                VHPIDIRECT  Tested on Linux, macOS and Windows
GHDL (mcode, llvm-jit, llvm, gcc)  VHPIDIRECT  Tested on Linux, macOS and Windows
Questa/ModelSim                    FLI         Tested manually on Linux; the Windows build is untested
Riviera-PRO, Active-HDL            VHPI        Untested; a subset of the API, see :doc:`other_simulators`
=================================  ==========  ========================================================

Getting started
---------------

.. code-block:: bash

    pip install vunit-python-bridge

The run script adds the package to the project:

.. code-block:: python

    from vunit import VUnit

    vu = VUnit.from_argv()
    vu.add_vhdl_builtins()
    vu.add_package("vunit-python-bridge", allow_setup=True)

    lib = vu.add_library("lib")
    lib.add_source_files("*.vhd")

    vu.main()

``allow_setup=True`` is required because, when added, the package builds its native library and
registers simulator options as part of its setup function, which VUnit only runs when the project
allows it.

``python_pkg`` and its foreign language interface, ``python_ffi_pkg``, then
become available through ``python_context``:

.. code-block:: vhdl

    library vunit_lib;
    context vunit_lib.vunit_context;

    library python_bridge;
    context python_bridge.python_context;

    ...

    exec("import numpy as np");
    result := eval("int(np.sum([1, 2, 3]))");

.. toctree::
   :caption: User guide
   :hidden:

   requirements
   running_code
   types
   errors
   sessions
   python_files
   file_paths

.. toctree::
   :caption: VHDL API reference
   :hidden:

   api/python_context
   api/python_ffi_pkg
   api/python_pkg

.. toctree::
   :caption: Simulators
   :hidden:

   how_it_works
   other_simulators

.. toctree::
   :caption: About
   :hidden:

   release_notes
   GitHub <https://github.com/VUnit/vunit-python-bridge>
