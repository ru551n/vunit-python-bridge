.. _python_bridge:sessions:

Sessions
--------

Every operation that runs Python code or evaluates a Python expression --
``exec``, ``eval``/``eval_<type>``, ``call``, ``exec_file``,
``import_run_script`` and ``import_module_from_file`` -- takes an optional
trailing parameter,
``session : python_session_t := default_session``, that selects the namespace
the operation runs in. A session is made with ``new_session`` and its Python
namespace is created the first time it is used; the ``default_session``
constant used when the parameter is omitted runs in ``__main__``.

.. code-block:: vhdl

    constant golden : python_session_t := new_session("golden");
    constant fixed_point : python_session_t := new_session("fixed_point");

    ...

    exec("x = 1", session => golden);
    exec_file("fixed_point.py", session => fixed_point);  -- <testbench directory>/fixed_point.py

    expected := eval("model(x)", session => golden);
    got := call("model", arg(x), session => fixed_point);

Since ``session`` comes after up to 10 positional arguments in ``call``, it is
normally given by name, as above. Both sessions in the example can define
``model`` without interfering with each other.

A session is a VUnit object with an `identity
<https://vunit.github.io/id/user_guide.html>`__ of its own, returned by
``get_id(session)``. ``new_session(name)`` creates the identity ``name`` under
``python_bridge:python``, the identity of ``python_logger``, while
``new_session(id)`` takes an identity that already exists and can therefore
place the session anywhere in the identity tree, for example under the identity
of what it serves:

.. code-block:: vhdl

    constant model_id : id_t := get_id("model", parent => get_id("my_testbench"));
    constant model : python_session_t := new_session(model_id);

Two sessions with the same identity are the same session, so a session does not
have to be passed around to be used in several places. ``name(session)`` is the
name of its identity without hierarchy, while the full name of the identity is
the key of its Python namespace. Two sessions with the same name but different
identities are therefore namespaces of their own.

Errors of an operation are reported on the logger of the identity of the
session it was performed in, ``get_logger(get_id(session))``. The loggers of
the sessions created from a name are children of ``python_logger``, so log
levels and log handler settings made on ``python_logger`` apply to them, but
mocking a logger does not capture what its children log. A test that mocks the
errors of a session mocks the logger of that session, the default session
included:

.. code-block:: vhdl

    constant default_logger : logger_t := get_logger(get_id(default_session));
    constant golden_logger : logger_t := get_logger(get_id(golden));

    ...

    mock(golden_logger, failure);

On Riviera-PRO/Active-HDL (VHPI), only the default session is supported:
passing any other session fails with a clear error.

.. _python_bridge:instance_sessions:

Independent models of component instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The bridge runs one Python interpreter per simulation, so a component with a
Python model that is instantiated more than once needs a session per instance
to give every instance a model state of its own. Without sessions, or with a
session made from a fixed name, all instances execute the model in the same
namespace and overwrite or share its functions and variables. The
``'instance_name`` attribute gives every instance a distinct identity to make
the session from:

.. code-block:: vhdl

    architecture python of accumulator_model is
    begin
      model : process is
        variable session : python_session_t;
      begin
        session := new_session(accumulator_model'instance_name);

        wait on x;
        exec_file(model_file, session);

        loop
          y <= call("accumulate", arg(x), session => session);
          wait on x;
        end loop;
      end process;
    end architecture;

Every instance executes the same file in its own session and passes that
session to every operation. The session is made in the statement part of the
process since GHDL leaves the instance labels out of ``'instance_name`` in a
declaration, which would give all instances the same session. A relative ``model_file`` is relative to the
testbench file (``tb_path``), which is only known after
``test_runner_setup``, so the file is executed when the first input arrives
rather than at the start of the simulation. The ``Test independent models of
two instances`` test case of the `embedded_python example
<https://github.com/VUnit/vunit-python-bridge/tree/main/examples/embedded_python>`__
drives two instances of this component, ``accumulator_model.vhd``, with
different inputs and checks that each keeps a total of its own.

An alternative is to define the model as a class and create one object per
session, keeping the mutable model state on ``self`` rather than in globals:

.. code-block:: python

    # accumulator.py
    class Accumulator:
        def __init__(self):
            self.total = 0

        def accumulate(self, x):
            self.total += x
            return self.total

.. code-block:: vhdl

    import_module_from_file(join(tb_path(runner_cfg), "accumulator.py"), "accumulator", session);
    exec("model = accumulator.Accumulator()", session);

    y <= call("model.accumulate", arg(x), session => session);

The module, and so the class, is shared by all sessions (see the caveats
below), while every session has a ``model`` object of its own. Like all
non-default sessions, this needs the Python bridge: NVC, GHDL or Questa.

Caveats
~~~~~~~

Sessions are separate namespaces in *one* Python interpreter, not separate
interpreters (which would not work with NumPy and many other extension
modules). Consequently, only the names defined by the executed code, such as
functions, classes and variables, are separate. Everything else is shared:

* Imported modules are loaded once and shared by all sessions. A module
  imported in one session is the same module object in another session, so
  changes to module state, such as ``np.random.seed(...)`` or attributes set
  on a module, are visible in all sessions. The same applies to sibling
  modules imported by a Python file executed in several sessions. State kept
  in the globals of an imported module is therefore not isolated by sessions.
* ``sys.path``, ``sys.modules``, environment variables, the current directory
  and open files are process wide. The current directory is the working
  directory of the simulator, see :ref:`python_bridge:file_paths`.
* Only the default session runs in ``__main__``. Classes defined in other
  sessions report ``__main__`` as their module but cannot be found there,
  which matters for example when pickling their instances.
* All sessions end with the simulation. Test cases run in the same simulation
  (``run_all_in_same_sim``) share the sessions.
