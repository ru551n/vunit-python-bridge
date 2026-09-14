# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com


"""
The VUnit package making Python callable from VHDL.

``vu.add_package("vunit-python-bridge", allow_setup=True)`` compiles
``python_pkg``/``python_context`` into the ``python_bridge`` library and sets up the foreign
language interface implementing them for the selected simulator:

* NVC, GHDL (VHPIDIRECT) and Questa/ModelSim (FLI) are served by the VUnit Python bridge, a
  small C library (native/*.c) embedding CPython in the simulator process.
* Riviera-PRO/Active-HDL are served by a VHPI application built with the simulator's own
  compiler driver.

Modules:

* bridge: setup of the bridge, its configuration and its generated VHDL.
* native_library: compiles and caches the library on Linux and macOS, selects the prebuilt
  DLL on Windows.
* foreign_application: builds the VHPI application.
* simulator_hooks: makes NVC and GHDL find the library.
* runtime: runs inside the simulator's embedded interpreter.
"""

import logging
import sys
from pathlib import Path

VHDL_PATH = Path(__file__).parent.resolve() / "vhdl" / "src"

# The foreign language interface implementing the package for a simulator. VUnit says which
# simulator was selected, the package says how it is served: NVC and GHDL both go through
# VHPIDIRECT but bind the library differently, Questa/ModelSim goes through the FLI and
# Riviera-PRO/Active-HDL through a VHPI application of their own.
FOREIGN_LANGUAGE_INTERFACES = {
    "nvc": "VHPIDIRECT_NVC",
    "ghdl": "VHPIDIRECT_GHDL",
    "modelsim": "FLI",
    "rivierapro": "VHPI",
    "activehdl": "VHPI",
}

# The simulators of the table, named as a user knows them
SUPPORTED_SIMULATORS = "NVC, GHDL, Questa/ModelSim, Riviera-PRO or Active-HDL"

LOGGER = logging.getLogger(__name__)


def setup(context):
    """
    Complete the addition of the package.

    ``vunit_pkg.toml`` lists the sources both variants of the package share, this adds the
    foreign language interface of the selected simulator: the VHPI application for
    Riviera-PRO/Active-HDL, the VUnit Python bridge for everyone else.
    """
    # pylint: disable=import-outside-toplevel
    from .bridge import setup as setup_bridge
    from .foreign_application import setup_vhpi_application
    from .native_library import PythonBridgeError
    from . import simulator_hooks

    simulator_name = context.simulator_name
    if simulator_name is None:
        raise RuntimeError(
            f"The vunit-python-bridge package requires {SUPPORTED_SIMULATORS} but no simulator was found"
        )

    interface = FOREIGN_LANGUAGE_INTERFACES.get(simulator_name)
    if interface is None:
        raise RuntimeError(
            f"The vunit-python-bridge package requires {SUPPORTED_SIMULATORS}, "
            f"it has no foreign language interface for {simulator_name}"
        )

    if interface == "VHPI":
        # Riviera-PRO/Active-HDL, the simulators served by the VHPI application
        context.add_source_files(context.library.name, [VHDL_PATH / "python_pkg_vhpi.vhd"])
        try:
            setup_vhpi_application(context.output_path, simulator_name, context.simulator_prefix)
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            sys.exit(1)
        return

    try:
        bridge = setup_bridge(
            context.output_path,
            context.run_script_path,
            simulator_name,
            context.simulator_prefix,
            context.simulator_backend,
        )
    except PythonBridgeError as exc:
        LOGGER.error("%s", exc)
        sys.exit(1)

    context.add_source_files(context.library.name, list(bridge.vhdl_files))

    simulator_hooks.register(context, bridge)
