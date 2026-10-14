Errors and semantics
====================

Errors
------

Python exceptions, syntax errors, type errors and undefined names are
reported as failures on the logger of the :ref:`session
<python_bridge:sessions>` the operation was performed in,
``get_logger(get_id(session))``, including the Python traceback. For the
default session that logger is named ``python_bridge:python:default`` and
``python_logger`` (named ``python_bridge:python``) is its parent. The test
fails and stops like for any other failure. The logger of the session can be
mocked to test error handling; when mocked, ``eval``/``call`` return a default
value (``0``, ``0.0``, ``""`` or an empty vector, depending on the type) after
the failure.

.. code-block:: text

    FAILURE - python_bridge:python:default - eval("1 / 0") failed:
    Traceback (most recent call last):
      File "<eval #3>", line 1, in <module>
        1 / 0
        ~~^~~
    ZeroDivisionError: division by zero

The default ``verbose`` format of the VUnit display handler indents the lines
of the traceback to the column where the message starts, after the time, the
logger name and the log level. With the long logger name of a session made from
an instance name and the absolute file paths of a traceback, the lines can be
wider than the terminal, which wraps them back to the first column and breaks
the alignment. The ``level`` format leaves out the time and the logger name and
indents the traceback by the width of the log level only:

.. code-block:: vhdl

    test_runner_setup(runner, runner_cfg);
    set_format(display_handler, level);

.. code-block:: text

    FAILURE - eval("1 / 0") failed:
              Traceback (most recent call last):
                File "<eval #3>", line 1, in <module>
                  1 / 0
                  ~~^~~
              ZeroDivisionError: division by zero

Output of ``print`` is written to the simulator output and flushed after
every operation.

.. _python_bridge:semantics:

Semantics to be aware of
-------------------------

.. important::

   * ``eval``/``eval_<type>`` are declared ``impure`` since they always read
     state from the Python interpreter.
   * Errors are reported as failures on the logger of the :ref:`session
     <python_bridge:sessions>`, including the Python traceback, rather than
     aborting the simulation.
   * ``python_setup`` and ``python_cleanup`` are optional, see
     :ref:`python_bridge:setup_and_cleanup`. ``python_cleanup`` does not
     finalize the interpreter.
   * ``real`` results have no float32 range limit: VHDL ``real`` is double
     precision where the Python bridge implements the API, so any finite
     Python ``float`` (also double precision) is in range. A value that is not
     finite, such as ``float("inf")`` or ``float("nan")``, has no VHDL ``real``
     representation and is reported as a failure.
   * ``string`` arguments are passed to Python double-quoted verbatim: a quote
     or backslash inside the string is not escaped, so it must be avoided or
     already be valid inside a Python double-quoted string.
