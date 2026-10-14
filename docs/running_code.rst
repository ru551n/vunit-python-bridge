Running Python code
===================

.. _python_bridge:setup_and_cleanup:

python_setup and python_cleanup
--------------------------------

Both are optional. ``python_setup`` starts the interpreter eagerly, otherwise
it starts on first use. ``python_cleanup`` releases the values staged for
``integer_array_t`` arguments early; they are released anyway when the
simulator process ends. It does *not* finalize the interpreter, so it is safe
to call even if more Python code runs afterwards (for example in another test
case of the same simulation). Output is flushed by every operation and does not
depend on ``python_cleanup``.

.. code-block:: vhdl

    test_runner_setup(runner, runner_cfg);
    python_setup;  -- Optional, the interpreter starts on first use

    ...

    python_cleanup;  -- Optional, releases the staged values early
    test_runner_cleanup(runner);

exec
----

``exec`` executes a string of Python source code in a persistent namespace
(``__main__`` by default, or another :ref:`session <python_bridge:sessions>`)
that lives until the simulation ends. Names defined by one ``exec`` are
therefore visible to later calls to ``exec`` and ``eval`` on the same session.

.. code-block:: vhdl

    exec("a = -17");
    check_equal(eval("abs(a)"), 17);

Multiline code can be written with an explicit ``LF``, or with the ``+``
operator that ``python_pkg`` defines for strings as a shorthand for ``& LF &``:

.. code-block:: vhdl

    exec(
      "def scale(x, gain):" & LF &
      "    return x * gain"
    );

    exec(
      "import numpy as np" +
      "" +
      "def fibonacci(n):" +
      "    a, b = 0, 1" +
      "    for _ in range(n):" +
      "        a, b = b, a + b" +
      "    return a"
    );

Indentation and blank lines (``""``) are preserved exactly. ``+`` only applies
where a ``string`` is expected; ``numeric_std`` arithmetic such as
``unsigned'("0011") + "0001"`` is unaffected.

eval
----

``eval`` evaluates a string containing a Python expression, in the default
session or another :ref:`session <python_bridge:sessions>`, and converts the
result to the VHDL type expected by the context, through one of these
functions (all aliased ``eval``):

* ``eval_integer``, returning ``integer``
* ``eval_real``, returning ``real``
* ``eval_string``, returning ``string``
* ``eval_integer_vector``, returning ``integer_vector``
* ``eval_real_vector``, returning ``real_vector``
* ``eval_integer_vector_ptr``, returning ``integer_vector_ptr_t``

.. code-block:: vhdl

    variable answer : integer;
    variable ratio : real;
    variable list : integer_vector_ptr_t;
  begin
    exec("from math import pi");
    answer := eval("6 * 7");
    ratio := eval("pi");
    list := eval("[1, 1, 2, 3, 5, 8]");

When the result type is not clear from the context (for example when it is
passed as an argument, or logged with ``info``), the explicit ``eval_<type>``
name selects the overload:

.. code-block:: vhdl

    info("pi = " & to_string(eval_real("pi")));

On NVC, GHDL and Questa, where the API is implemented by the VUnit Python
bridge, ``eval`` has more result types:

* ``eval_boolean``, returning ``boolean``. Only ``bool``/``numpy.bool_`` is
  accepted. It also makes the result of ``eval`` usable as a condition:
  ``if eval("model.is_done()") then``.
* ``eval_std_ulogic``, returning ``std_ulogic``.
* ``eval_std_ulogic_vector``, returning an unconstrained ``std_ulogic_vector``.
* ``eval_integer_array``, returning ``integer_array_t``, see
  :ref:`python_bridge:integer_array`.

``eval_boolean`` and ``eval_std_ulogic`` are aliased ``eval`` like the other
result types. ``eval_std_ulogic_vector`` and ``eval_integer_array`` are not,
since that would make ``check_equal(eval("17"), 17)`` and
``length(eval("[1, 2]"))`` ambiguous: use their explicit names.

``std_ulogic_vector``, ``signed`` and ``unsigned`` results are also available
as the procedures ``eval_std_ulogic_vector``, ``eval_signed`` and
``eval_unsigned``, that take the result as an ``out`` parameter. The width is
given by the actual, and a Python value that does not fit that width is an
error. ``signed`` and ``unsigned`` results are only available in the
procedure form, since a function cannot know the width of the result.

.. code-block:: vhdl

    variable byte : std_ulogic_vector(7 downto 0);
    variable level : signed(15 downto 0);
  begin
    eval_std_ulogic_vector("format(value, '08b')", byte);
    eval_signed("model.level()", level);

call, arg, kwarg and to_call_str
---------------------------------

``call`` calls a Python function (or a callable expression such as a dotted
name, ``"np.sum"``, or a method, ``"model.run"``) with up to 10 arguments,
built with ``arg`` (positional) and ``kwarg`` (keyword), and converts the
returned value like ``eval``. Like every other operation, it accepts an
optional trailing :ref:`session <python_bridge:sessions>` parameter, normally
given by name since it follows the positional arguments:

.. code-block:: vhdl

    variable gcd, count : integer;
    variable ratio : real;
  begin
    exec("from math import gcd as py_gcd");
    gcd := call("py_gcd", arg(35), arg(77), arg(119));
    ratio := call("round", arg(3.14159), kwarg("ndigits", 3));

    -- No return value: the procedure form of call
    call("print", arg(35), arg(77), arg(119));

``arg`` and ``kwarg`` accept these value types:

========================== ========================================================
VHDL                       Python
========================== ========================================================
``integer``                ``int``
``real``                   ``float``
``boolean``                ``bool``
``string``                 ``str``
``integer_vector``         ``list`` of ``int``
``real_vector``            ``list`` of ``float``
``integer_vector_ptr_t``   ``list`` of ``int``
``std_ulogic``              ``bool``, 1 and H give ``True``, 0 and L give ``False``
``unsigned``               ``int``, passed as ``arg_unsigned``/``kwarg_unsigned``
``signed``                 ``int``, passed as ``arg_signed``/``kwarg_signed``
``integer_array_t``        NumPy array, not on Riviera-PRO/Active-HDL
========================== ========================================================

An ``unsigned`` or ``signed`` value of any width becomes an exact Python
integer, so it is not limited to the range of a VHDL ``integer``. The two have
names of their own rather than ``arg`` overloads, since a string literal
belongs to every character array type and an overload would therefore make
``arg("hello")`` ambiguous. ``H`` and ``L`` are read as 1 and 0 in a
``std_ulogic``, ``unsigned`` or ``signed`` value; any other metavalue is an
error.

A value that cannot be converted has no session and is reported as a failure
on ``python_logger`` itself. The argument becomes an expression raising the
same message in Python. The call it is used in therefore fails with that
message as well instead of being made without the argument, which is what would
otherwise happen when the logger is mocked and the simulation continues:

.. code-block:: text

    FAILURE - python_bridge:python - arg cannot convert 'X'; expected '0', '1', 'L' or 'H'
    FAILURE - python_bridge:python:default - eval("model(__vunit__.error("arg cannot convert 'X'; ..."))") failed:
    Traceback (most recent call last):
      ...
    RuntimeError: arg cannot convert 'X'; expected '0', '1', 'L' or 'H'

An aggregate or a literal does not select an overload by itself and needs a
qualified expression: ``arg(real_vector'(1.0, 2.0))``,
``arg(integer_vector'(1, 2, 3))``. There is no ``std_ulogic_vector`` value,
which would be ambiguous for the same reason as ``unsigned``. Such a value is
passed as a number or as the string of its characters:

.. code-block:: vhdl

    call("model.scale", arg_unsigned(unsigned(gain)));
    call("model.push", arg(to_string(slv)));

On NVC, GHDL and Questa, ``call`` returns the same types as ``eval``:
``call_boolean``, ``call_std_ulogic``, ``call_std_ulogic_vector``,
``call_integer_array``, ``call_string``, ``call_real_vector`` and
``call_integer_vector_ptr``, plus the procedures ``call_std_ulogic_vector``,
``call_signed`` and ``call_unsigned`` taking the result as an ``out``
parameter. All of the functions but ``call_std_ulogic_vector`` are aliased
``call``.

``to_call_str`` builds the Python call expression itself, as a string, which
is useful to embed a call inside a larger ``exec``/``eval`` string:

.. code-block:: vhdl

    exec("gcd = " & to_call_str("py_gcd", arg(35), arg(77)));

Every unused trailing argument of ``call``/``to_call_str`` defaults to an
ignored placeholder, so calls with fewer than 10 arguments need no padding.

Argument groups
~~~~~~~~~~~~~~~~

Arguments combined with ``&`` become a single argument, which makes it
possible to pass more than 10 arguments and to build the arguments of a call
in steps:

.. code-block:: vhdl

    -- Calls plot(data, **dict(title="Step response", grid=True))
    call("plot", arg(data), kwarg("title", string'("Step response")) & kwarg("grid", true));

    -- Calls scale(*(1, 2,), **dict(gain=3))
    call("scale", arg(1) & arg(2) & kwarg("gain", 3));

A group of positional arguments is passed to Python as ``*(1, 2,)``, a group
of keyword arguments as ``**dict(a=1, b=2)`` and a group of both as
``*(1,), **dict(a=1)``. It uses one of the 10 argument slots, no matter how
many arguments it holds, and keeps Python's own rules: a group with keyword
arguments must come after the positional arguments of the call and a keyword
must not be repeated within it. Appending a positional argument to a group
that already has keyword arguments is an error for the same reason, reported
as ``positional argument after keyword arguments``.

``null_arg`` is the identity of the operation. That is what makes a group
possible to build one argument at a time, ending with ``null_arg``, and what
lets a helper that contributes an optional argument return ``null_arg`` when
it has none. An empty group is a call with no arguments rather than an error.
Since ``arg_t`` holds unconstrained strings, a group is grown by a function
rather than by assigning to a variable in a loop:

.. code-block:: vhdl

    -- The registers from idx and up, an empty group when there are none
    impure function registers(idx : natural) return arg_t is
    begin
      if idx = num_registers then
        return null_arg;
      end if;
      return kwarg(name(idx), value(idx)) & registers(idx + 1);
    end;

    ...

    call("model.configure", registers(0));
