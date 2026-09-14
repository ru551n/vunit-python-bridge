# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com


"""
Simulator hooks making the simulator load the bridge library and its dependencies.

They are registered with the package context by the setup function of the package, one set
per simulator, and are only called for the project they were registered for.

Questa needs no help finding the library itself: the FLI attributes of the generated
python_bridge_pkg.vhd name it by absolute path.
"""

import os
import sys
from typing import Dict, List

from .bridge import GHDL_LINKING_BACKENDS, PythonBridge


def register(context, bridge: PythonBridge) -> None:
    """
    Register the hooks of every simulator the bridge serves with the package context.
    """
    context.register_simulator_hooks("nvc", run_flags=_nvc_run_flags(bridge))
    context.register_simulator_hooks(
        "ghdl",
        elab_flags=_ghdl_elab_flags(bridge),
        run_env=_ghdl_run_env(bridge),
    )
    context.register_simulator_hooks("modelsim", run_flags=_modelsim_run_flags(bridge))


def _nvc_run_flags(bridge: PythonBridge):
    """
    NVC run (-r) flags loading the bridge.
    """

    def hook(simulator_interface) -> List[str]:  # pylint: disable=unused-argument
        return [f"--load={bridge.library_file!s}"]

    return hook


def _ghdl_elab_flags(bridge: PythonBridge):
    """
    GHDL elaboration flags. Only ahead-of-time linking backends need them.
    """

    def hook(simulator_interface) -> List[str]:  # pylint: disable=unused-argument
        if bridge.ghdl_backend not in GHDL_LINKING_BACKENDS:
            return []
        return [f"-Wl,-L{bridge.directory!s}"]

    return hook


def _ghdl_run_env(bridge: PythonBridge):
    """
    Add the bridge directory to the dynamic library search path of a GHDL simulation.
    """

    def hook(simulator_interface, env: Dict[str, str]) -> Dict[str, str]:  # pylint: disable=unused-argument
        variable = {"win32": "PATH", "darwin": "DYLD_LIBRARY_PATH"}.get(sys.platform, "LD_LIBRARY_PATH")
        env = dict(env)
        env[variable] = os.pathsep.join(item for item in (str(bridge.directory), env.get(variable, "")) if item)
        return env

    return hook


def _modelsim_run_flags(bridge: PythonBridge):  # pylint: disable=unused-argument
    """
    Flags for the vsim command of a Questa/ModelSim simulation.

    Questa/ModelSim puts the directory of the C++ runtime it bundles first in
    LD_LIBRARY_PATH. That runtime is regularly older than the one the Python extension
    modules of the environment (NumPy, used for integer_array_t values) were built
    against, and they then fail to load in the embedded interpreter. -noautoldlibpath
    turns that off, leaving the C++ runtime of the system to be found as usual.

    Only relevant on Linux, where LD_LIBRARY_PATH decides this.
    """

    def hook(simulator_interface) -> List[str]:  # pylint: disable=unused-argument
        if not sys.platform.startswith("linux"):
            return []
        return ["-noautoldlibpath"]

    return hook
