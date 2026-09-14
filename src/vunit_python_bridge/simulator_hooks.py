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
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .bridge import GHDL_LINKING_BACKENDS, PythonBridge

# The vsim flag keeping the runtime libraries Questa bundles out of the dynamic library
# search path, and the help category listing every vsim flag.
NO_AUTO_LD_LIBRARY_PATH = "-noautoldlibpath"
VSIM_HELP_ARGUMENTS = ("-help", "all")


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
    context.register_simulator_hooks("modelsim", process_flags=_modelsim_process_flags())


def _nvc_run_flags(bridge: PythonBridge):
    """
    NVC run (-r) flags loading the bridge.
    """

    def hook(simulator_interface) -> List[str]:  # pylint: disable=unused-argument
        return [f"--load={bridge.library_file!s}"]

    return hook


def _ghdl_elab_flags(bridge: PythonBridge):
    """
    GHDL elaboration flags. Only the backends linking the design ahead of time need them,
    the others load the bridge at run time and are served by the run environment.
    """

    def hook(simulator_interface) -> List[str]:
        if simulator_interface.backend not in GHDL_LINKING_BACKENDS:
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


def _modelsim_process_flags():
    """
    Flags for the vsim process VUnit starts for a Questa/ModelSim simulation.

    Questa/ModelSim puts the directory of the C++ runtime it bundles first in
    LD_LIBRARY_PATH. That runtime is regularly older than the one the Python extension
    modules of the environment (NumPy, used for integer_array_t values) were built
    against, and they then fail to load in the embedded interpreter. -noautoldlibpath
    turns that off, leaving the C++ runtime of the system to be found as usual.

    The flag is set up when the process starts, so it is only honoured on the command line
    of the vsim process itself, not on the vsim command of the do-file VUnit generates.

    Only relevant on Linux, where LD_LIBRARY_PATH decides this, and only given to a vsim
    that knows the flag.
    """
    known: Dict[Optional[str], bool] = {}

    def hook(simulator_interface) -> List[str]:
        if not sys.platform.startswith("linux"):
            return []

        prefix = simulator_interface.prefix
        if prefix not in known:
            known[prefix] = _vsim_knows_flag(prefix, simulator_interface)
        if not known[prefix]:
            return []

        return [NO_AUTO_LD_LIBRARY_PATH]

    return hook


def _vsim_knows_flag(prefix: Optional[str], simulator_interface) -> bool:
    """
    Whether the vsim of an installation lists -noautoldlibpath among its options.

    Asking vsim rather than assuming keeps a version without the flag from failing to
    start at all. An installation that cannot be asked is taken to know it, since the
    flag is what makes the bridge usable there.
    """
    if prefix is None:
        return True

    try:
        output = subprocess.run(
            [str(Path(prefix) / "vsim"), *VSIM_HELP_ARGUMENTS],
            check=True,
            capture_output=True,
            text=True,
            env=simulator_interface.get_env(),
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return True

    return NO_AUTO_LD_LIBRARY_PATH in output.split()
