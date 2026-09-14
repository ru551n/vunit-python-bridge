# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com


"""
The VUnit package making Python callable from VHDL.

``vu.add_package("vunit-python-bridge")`` compiles ``python_pkg``/``python_context`` into the
``python_bridge`` library and sets up the foreign language interface implementing them for the
selected simulator:

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

# Foreign language interfaces the package can be implemented with
SUPPORTED_FOREIGN_LANGUAGE_INTERFACES = {"VHPI", "FLI", "VHPIDIRECT_NVC", "VHPIDIRECT_GHDL"}

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

    simulator_class = context.simulator_class
    if simulator_class is None:
        raise RuntimeError(
            "The vunit-python-bridge package requires a simulator supporting one of "
            f"{', '.join(sorted(SUPPORTED_FOREIGN_LANGUAGE_INTERFACES))} but no simulator was found"
        )

    supported = set(simulator_class.supported_foreign_language_interfaces())
    if not SUPPORTED_FOREIGN_LANGUAGE_INTERFACES & supported:
        raise RuntimeError(
            "The vunit-python-bridge package requires support for one of "
            f"{', '.join(sorted(SUPPORTED_FOREIGN_LANGUAGE_INTERFACES))} "
            f"but {simulator_class.name} supports none of them"
        )

    if "VHPI" in supported:
        # Riviera-PRO/Active-HDL, the simulators served by the VHPI application
        context.add_source_files(context.library.name, [VHDL_PATH / "python_pkg_vhpi.vhd"])
        try:
            setup_vhpi_application(context.output_path, simulator_class)
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            sys.exit(1)
        return

    try:
        bridge = setup_bridge(context.output_path, simulator_class, context.run_script_path)
    except PythonBridgeError as exc:
        LOGGER.error("%s", exc)
        sys.exit(1)

    context.add_source_files(context.library.name, list(bridge.vhdl_files))

    simulator_hooks.register(context, bridge)
