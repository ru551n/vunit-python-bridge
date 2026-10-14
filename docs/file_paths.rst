.. _python_bridge:file_paths:

File paths
----------

A file name can be resolved against several directories, depending on who
resolves it: ``python_pkg`` in VHDL, or Python code in the model. This section
lists them all, gives recipes for the common cases and describes ``base_path``,
which gives verification components a directory of their own.

How a file name is resolved
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - File name
     - Resolved against
   * - Relative name given to ``exec_file`` or ``import_module_from_file``
       after ``test_runner_setup`` has completed
     - The directory of the testbench file, ``tb_path``.
   * - The same before ``test_runner_setup`` has completed, or without a
       test runner
     - Nothing: it is reported as a failure, which suggests calling it after
       ``test_runner_setup``, giving an absolute name or joining it to
       ``base_path``.
   * - Absolute name given to ``exec_file`` or ``import_module_from_file``
     - Used as it is given.
   * - ``join(base_path, "x")``, at any time, time 0 included
     - The base directory set by ``set_relative_file_base`` in the run script
       or by the environment variable ``VUNIT_PYTHON_BRIDGE_FILE_BASE``, which
       ``base_path`` returns. Without a base directory ``base_path`` is
       reported as a failure.
   * - Relative name opened by Python code: ``open``, ``numpy.load``,
       ``pathlib.Path`` and so on
     - The current working directory of Python, which is the working
       directory of the simulator. See the warning below.
   * - Python module imported by name, ``import model``
     - ``sys.path``, which holds the directory of the run script first, like
       ``python run.py`` does, the directories of ``PYTHONPATH`` (the
       simulator inherits the environment of VUnit, so a ``PYTHONPATH`` set
       in the run script before ``vu.main()`` is seen), and, while
       ``exec_file`` executes a file, the directory of that file.

.. warning::

   The working directory of the simulator differs between simulators. On NVC
   and GHDL it is the directory the run script was started from. On
   Questa/ModelSim it is the ``modelsim`` directory of the VUnit output path,
   for example ``vunit_out/modelsim``. Other simulators may use yet another
   directory. Never rely on a relative file name in Python code: build it from
   ``Path(__file__).parent`` in the model, or pass an absolute name from VHDL,
   built with ``base_path`` or ``tb_path``.

Recipes
~~~~~~~

**A Python file next to the testbench.** Give its name relative to the
testbench file, after ``test_runner_setup``:

.. code-block:: vhdl

    test_runner_setup(runner, runner_cfg);
    exec_file("model.py");  -- <testbench directory>/model.py

**The model of a verification component.** A verification component is not
tied to a testbench and often loads its model at time 0, before
``test_runner_setup``. Give its name relative to a base directory set in the
run script. With this layout:

.. code-block:: text

    project/
      run.py
      vc/
        uart_vc.vhd
        models/
          uart_model.py
          helpers.py
      tb/
        tb_uart.vhd

the run script sets its own directory as the base directory, which makes the
names independent of the directory the run script is started from:

.. code-block:: python

    import vunit_python_bridge

    # project/, whatever the working directory
    vunit_python_bridge.set_relative_file_base(Path(__file__).parent)
    vu.add_package("vunit-python-bridge", allow_setup=True)

.. code-block:: vhdl

    exec_file(join(base_path, "vc/models/uart_model.py"), session);  -- project/vc/models/uart_model.py
    import_module_from_file(join(base_path, "vc/models/helpers.py"), "helpers", session);  -- project/vc/models/helpers.py

Alternatively, import the model by module name from a directory on
``sys.path``: the directory of the run script, or one added to ``PYTHONPATH``
in the run script before ``vu.main()``:

.. code-block:: python

    # project/vc/models on sys.path of the simulator
    os.environ["PYTHONPATH"] = str(Path(__file__).parent / "vc" / "models")

.. code-block:: vhdl

    exec("import uart_model", session);  -- found on sys.path: project/vc/models/uart_model.py

Or wait for ``test_runner_setup`` to complete and give the name relative to the
testbench file:

.. code-block:: vhdl

    if get_phase <= test_runner_setup then
      wait on runner until get_phase > test_runner_setup;
    end if;
    exec_file("uart_model.py", session);  -- <testbench directory>/uart_model.py

``wait_until(runner, test_runner_setup)`` is not enough, since the phase is
entered before the testbench path is set.

**Data files used by a model.** Find them relative to the model file in
Python:

.. code-block:: python

    from pathlib import Path

    # Next to this file, whatever the working directory of the simulator
    COEFFICIENTS = np.load(Path(__file__).parent / "coefficients.npy")

or pass an absolute name from VHDL:

.. code-block:: vhdl

    -- project/vc/data/coefficients.npy, an absolute name for Python
    call("model.load_coefficients", arg(join(base_path, "vc/data/coefficients.npy")));

**A run script shared through a git submodule.** When the run script cannot be
changed, set the base directory with the environment variable, for example from
a Makefile at the root of the repository:

.. code-block:: text

    repo/
      Makefile
      sub/            (git submodule)
        run.py
        vc/
          models/
            vc_model.py
      tb/
        tb_vc.vhd

.. code-block:: make

    # repo/ is the base directory
    sim:
    	VUNIT_PYTHON_BRIDGE_FILE_BASE=$(CURDIR) python sub/run.py

The file names joined to ``base_path`` are then relative to the repository
root:

.. code-block:: vhdl

    exec_file(join(base_path, "sub/vc/models/vc_model.py"));  -- repo/sub/vc/models/vc_model.py

base_path and the base directory
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``base_path`` returns the base directory, absolute, for VHDL to join file
names to with ``join`` of VUnit's ``path`` package, which ``vunit_context``
includes, the same way as ``tb_path(runner_cfg)``. It is a function without
arguments: the base directory is a constant of a package generated when the
package is set up, so it can be used at any time, before ``test_runner_setup``
too. Without a base directory ``base_path`` is reported as a failure on
``python_logger``, naming both ways of setting it, and returns ``""``.
``base_path`` serves any file name passed to a Python model, not only those of
``exec_file`` and ``import_module_from_file``, whose own relative file names
are still taken from the directory of the testbench.

``vunit_python_bridge.set_relative_file_base(directory)`` sets the base
directory in the run script. It must be called before
``vu.add_package("vunit-python-bridge", ...)``; a call after it raises a
``RuntimeError``. The directory, a ``str`` or a ``Path``, is resolved when the
function is called, a relative one against the current working directory, and
a directory that does not exist raises a ``ValueError``.

The environment variable ``VUNIT_PYTHON_BRIDGE_FILE_BASE`` sets the base
directory without changing the run script. It is read when the package is set
up, during ``add_package``. A relative value is resolved against the current
working directory at that time, an empty value counts as unset, and a value
that is not an existing directory makes the setup fail with an error naming
the variable and the value.

The variable takes precedence, so that whoever runs a shared run script can
override the directory it sets:

==========================  ====================  ==========================
``set_relative_file_base``  Environment variable  Base directory
==========================  ====================  ==========================
not called                  unset or empty        none, ``base_path`` fails
called                      unset or empty        that of the call
not called                  set                   that of the variable
called                      set                   that of the variable
==========================  ====================  ==========================

When both are set to different directories, compared after resolving them,
the setup logs a warning naming both and saying that the environment variable
takes precedence.
