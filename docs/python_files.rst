Python files and modules
========================

exec_file
---------

``exec_file`` executes a Python file (where the Python bridge implements the
API: NVC, GHDL and Questa), with the equivalent of

.. code-block:: python

    with open(path, encoding="utf-8") as file:
        source = file.read()
    exec(compile(source, str(path), "exec"), namespace, namespace)

which means that tracebacks show the real file name and line numbers,
``__file__`` is set to the absolute path of the file while it executes (and
restored afterwards), and the directory of the file is added to ``sys.path``
while it executes so that it can import sibling modules without setting
``PYTHONPATH``. Imports are therefore expected at the top level of the file.
Executing the same file twice executes it twice.

A relative file name is relative to the directory of the testbench file,
``tb_path``, and needs ``test_runner_setup`` to have completed; an absolute
file name is used as given. See :ref:`python_bridge:file_paths` for loading a
file at any other time, for example from a verification component. Like the
other operations, it takes an optional trailing :ref:`session
<python_bridge:sessions>` parameter.

import_run_script
------------------

``import_run_script`` imports the VUnit run script as a Python module, so
that functions and classes defined in it (for example a plot helper using
matplotlib) can be called from VHDL without duplicating them in a separate
file:

.. code-block:: vhdl

    import_run_script;
    exec("run.hello_world()");

    import_run_script("my_run_script");
    exec("my_run_script.hello_world()");

Without an explicit name, the module is named after the run script's file
name (without extension), so the run script is normally named ``run.py``. The
run script is found by its absolute path, and its directory is on ``sys.path``
so that it can import its siblings, see :ref:`python_bridge:file_paths`.
Because the run script is imported as a module, it must be import-safe: code
that is only meant to run when the script is invoked directly (typically the
call to ``vu.main()``) must be behind
``if __name__ == "__main__":``; a run script without such a guard is
rejected before it is imported. Like the other operations, it takes an
optional trailing :ref:`session <python_bridge:sessions>` parameter.

import_module_from_file and to_py_list_str
--------------------------------------------

``import_module_from_file`` imports any Python file as a module by path (also
taking an optional :ref:`session <python_bridge:sessions>` parameter), and is
what ``import_run_script`` uses internally. Like the file name of
``exec_file``, a relative path is relative to the directory of the testbench
file, ``tb_path``, and needs ``test_runner_setup`` to have completed; an
absolute path is used as it is given. See :ref:`python_bridge:file_paths` for
importing a file at any other time, for example from a verification
component:

.. code-block:: vhdl

    import_module_from_file("reference_model.py", "reference_model");  -- <testbench directory>/reference_model.py
    exec("reference_model.configure(gain=4)");

``to_py_list_str`` converts an ``integer_vector``, ``integer_vector_ptr_t`` or
``real_vector`` to the string representation of the equivalent Python list,
for use in ``exec``/``eval`` strings:

.. code-block:: vhdl

    exec("a_list = " & to_py_list_str(integer_vector'(1, 2, 3, 4)));
    check_equal(eval("sum(a_list)"), 10);
