# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2026, Lars Asplund lars.anders.asplund@gmail.com

"""
Test the vunit-python-bridge package (src/vunit_python_bridge)

These tests must never invoke an HDL simulator. Compiling the small C bridge
library with the system C compiler, and reading/writing files, is fine.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import contextmanager
from glob import glob
from pathlib import Path
from unittest import mock

import vunit_python_bridge
from vunit_python_bridge import bridge as bridge_setup, foreign_application, native_library, simulator_hooks

PACKAGE_ROOT = Path(vunit_python_bridge.__file__).parent.resolve()
MANIFEST = PACKAGE_ROOT / "vunit_pkg.toml"


@contextmanager
def create_tempdir():
    """
    A temporary directory as a Path.
    """
    with tempfile.TemporaryDirectory() as name:
        yield Path(name).resolve()


# The complete VHPIDIRECT contract between python_bridge_pkg.vhd.in and
# native/*.c. The generated VHDL and the built library must agree on it
# exactly: nothing else may be exported.
EXPECTED_EXPORTS = (
    "vpy_setup",
    "vpy_cleanup",
    "vpy_buffer_clear",
    "vpy_buffer_append",
    "vpy_begin",
    "vpy_execute",
    "vpy_eval",
    "vpy_push_array",
    "vpy_array_write",
    "vpy_stage",
    "vpy_result_integer",
    "vpy_result_real",
    "vpy_result_meta",
    "vpy_result_read_string",
    "vpy_result_read_integers",
    "vpy_result_read_reals",
    "vpy_error_length",
    "vpy_error_read",
)


def _write_run_script(path: Path) -> Path:
    """
    A stub run script; its directory is put on sys.path by the runtime.
    """
    path.write_text("# run script stub\n", encoding="utf-8")
    return path


class _FakeLibrary:
    """
    The Library object of the package, as seen through the package context.
    """

    def __init__(self, name="python_bridge"):
        self.name = name


class _FakeContext:
    """
    A stand-in for vunit.package_context.PackageContext.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, simulator_class, output_path, run_script_path, simulator_prefix=None, simulator_backend=None
    ):
        self.simulator_class = simulator_class
        self.output_path = output_path
        self.run_script_path = run_script_path
        self.simulator_prefix = simulator_prefix
        self.simulator_backend = simulator_backend
        self.library = _FakeLibrary()
        self.added_files = []
        self.hooks = {}

    @property
    def simulator_name(self):
        return None if self.simulator_class is None else self.simulator_class.name

    def add_source_files(self, library_name, pattern, vhdl_standard=None):
        self.added_files += [(library_name, Path(item)) for item in pattern]

    def register_simulator_hooks(
        self, simulator_name, *, elab_flags=None, run_flags=None, process_flags=None, run_env=None
    ):
        self.hooks[simulator_name] = dict(
            elab_flags=elab_flags, run_flags=run_flags, process_flags=process_flags, run_env=run_env
        )


class TestManifest(unittest.TestCase):
    """
    vunit_pkg.toml: what VUnit reads before the setup function is called.
    """

    def setUp(self):
        with MANIFEST.open("rb") as fptr:
            self.package = tomllib.load(fptr)["package"]

    def test_library_is_python_bridge(self):
        self.assertEqual(self.package["library"], "python_bridge")

    def test_setup_points_at_the_setup_function(self):
        self.assertEqual(self.package["setup"], "vunit_python_bridge:setup")
        module_name, function_name = self.package["setup"].split(":")
        self.assertEqual(module_name, vunit_python_bridge.__name__)
        self.assertIs(getattr(vunit_python_bridge, function_name), vunit_python_bridge.setup)

    def test_requires_vhdl_2008(self):
        self.assertEqual(self.package["requires-vhdl"], ">=2008")

    def test_requires_a_vunit_version(self):
        self.assertTrue(self.package["requires-vunit"].startswith(">="))

    def test_sources_are_the_simulator_independent_vhdl(self):
        includes = [item for source in self.package["sources"] for item in source["include"]]
        self.assertEqual(
            sorted(includes),
            ["vhdl/src/python_context.vhd", "vhdl/src/python_pkg.vhd"],
        )
        for include in includes:
            self.assertTrue((PACKAGE_ROOT / include).is_file(), include)

    def test_the_simulator_dependent_vhdl_is_not_listed(self):
        includes = [item for source in self.package["sources"] for item in source["include"]]
        for name in ("python_pkg_vhpi.vhd", "python_ffi_pkg_bridge.vhd"):
            self.assertNotIn(f"vhdl/src/{name}", includes)


class TestForeignLanguageInterfaces(unittest.TestCase):
    """
    The table deciding how a simulator is served. VUnit only says which simulator was
    selected, so the package has to know the foreign language interface of each of them.
    """

    def test_every_supported_simulator_has_its_interface(self):
        self.assertEqual(
            vunit_python_bridge.FOREIGN_LANGUAGE_INTERFACES,
            {
                "nvc": "VHPIDIRECT_NVC",
                "ghdl": "VHPIDIRECT_GHDL",
                "modelsim": "FLI",
                "rivierapro": "VHPI",
                "activehdl": "VHPI",
            },
        )

    def test_the_simulators_the_bridge_serves_are_the_ones_it_is_set_up_for(self):
        # Everything that is not the VHPI application is served by the bridge, which has
        # to know the same simulators.
        served_by_the_bridge = {
            name
            for name, interface in vunit_python_bridge.FOREIGN_LANGUAGE_INTERFACES.items()
            if interface != "VHPI"
        }
        self.assertEqual(served_by_the_bridge, set(bridge_setup.BRIDGE_SIMULATORS))

    def test_the_message_names_every_simulator(self):
        for simulator in ("NVC", "GHDL", "Questa/ModelSim", "Riviera-PRO", "Active-HDL"):
            self.assertIn(simulator, vunit_python_bridge.SUPPORTED_SIMULATORS)


class TestPackageSetup(unittest.TestCase):
    """
    vunit_python_bridge.setup(context): the foreign language interface of the selected
    simulator is added on top of the sources of vunit_pkg.toml, with bridge.setup()
    stubbed so no compilation happens here.
    """

    def setUp(self):
        self.tempdir_cm = create_tempdir()
        self.tempdir = self.tempdir_cm.__enter__()
        self.addCleanup(self.tempdir_cm.__exit__, None, None, None)
        self.run_script = _write_run_script(self.tempdir / "run.py")

    def _context(self, simulator_class, prefix="/sim/bin", backend=None):
        return _FakeContext(simulator_class, self.tempdir / "out", self.run_script, prefix, backend)

    @staticmethod
    def _simulator(name):
        """
        A simulator interface class as the setup function sees it, that is by name.
        """
        simulator = mock.Mock()
        simulator.name = name
        return simulator

    def _added_names(self, context):
        return {path.name for _, path in context.added_files}

    def test_rejects_simulator_class_none(self):
        with self.assertRaisesRegex(RuntimeError, "no simulator was found"):
            vunit_python_bridge.setup(self._context(None))

    def test_rejects_unsupported_simulator(self):
        context = self._context(self._simulator("some_simulator"))
        with self.assertRaisesRegex(RuntimeError, "no foreign language interface for some_simulator") as ctx:
            vunit_python_bridge.setup(context)
        # The message names the simulators so a user knows what is supported.
        self.assertIn(vunit_python_bridge.SUPPORTED_SIMULATORS, str(ctx.exception))

    def test_vhpi_adds_python_pkg_vhpi_and_builds_the_application(self):
        for name in ("rivierapro", "activehdl"):
            self._check_vhpi_application_built(name)

    def _check_vhpi_application_built(self, name):
        simulator = self._simulator(name)
        context = self._context(simulator)
        with mock.patch("vunit_python_bridge.bridge.setup") as setup_mock, mock.patch(
            "vunit_python_bridge.foreign_application.setup_vhpi_application"
        ) as vhpi_mock:
            vunit_python_bridge.setup(context)
        setup_mock.assert_not_called()
        vhpi_mock.assert_called_once_with(context.output_path, name, context.simulator_prefix)

        self.assertEqual(self._added_names(context), {"python_pkg_vhpi.vhd"})
        self.assertEqual({library for library, _ in context.added_files}, {"python_bridge"})
        # The VHPI application needs no simulator hooks
        self.assertEqual(context.hooks, {})

    def test_application_build_failure_is_reported(self):
        context = self._context(self._simulator("rivierapro"))
        with mock.patch(
            "vunit_python_bridge.foreign_application.setup_vhpi_application",
            side_effect=RuntimeError("no compiler"),
        ), mock.patch("vunit_python_bridge.LOGGER") as logger:
            with self.assertRaises(SystemExit):
                vunit_python_bridge.setup(context)
        logger.error.assert_called_once_with("%s", mock.ANY)

    def _fake_bridge(self):
        return bridge_setup.PythonBridge(
            library_file=Path("/fake/cache/libvunit_python_bridge.so"),
            vhdl_files=[
                Path("/fake/out/python_bridge/vhdl/python_bridge_pkg.vhd"),
                bridge_setup.VHDL_SOURCE_PATH / "python_ffi_pkg_bridge.vhd",
            ],
        )

    def _check_bridge_files_added(self, simulator, backend=None):
        """
        The generated bridge files, and not the VHPI application package, are added
        for a simulator served by the Python bridge.
        """
        context = self._context(simulator, backend=backend)
        fake_bridge = self._fake_bridge()
        with mock.patch("vunit_python_bridge.bridge.setup", return_value=fake_bridge) as setup_mock:
            vunit_python_bridge.setup(context)

        # The bridge must be handed the output path, the run script path (whose directory
        # the runtime puts on sys.path, like python does for a run script) and the
        # simulator as the context knows it: its name, prefix and backend.
        setup_mock.assert_called_once_with(
            context.output_path,
            context.run_script_path,
            simulator.name,
            context.simulator_prefix,
            context.simulator_backend,
        )

        for expected in fake_bridge.vhdl_files:
            self.assertIn(("python_bridge", expected), context.added_files)
        self.assertNotIn("python_pkg_vhpi.vhd", self._added_names(context))
        return context

    def test_vhpidirect_adds_the_bridge_files(self):
        self._check_bridge_files_added(self._simulator("nvc"))
        self._check_bridge_files_added(self._simulator("ghdl"), backend="mcode")

    def test_fli_adds_the_bridge_files(self):
        # Questa/ModelSim is served by the bridge too, through native/fli.c.
        self._check_bridge_files_added(self._simulator("modelsim"))

    def test_fli_uses_the_bridge_not_the_vhpi_application(self):
        context = self._context(self._simulator("modelsim"))
        with mock.patch("vunit_python_bridge.bridge.setup", return_value=self._fake_bridge()), mock.patch(
            "vunit_python_bridge.foreign_application.setup_vhpi_application"
        ) as vhpi_mock:
            vunit_python_bridge.setup(context)
        vhpi_mock.assert_not_called()

    def test_hooks_are_registered_for_every_simulator_the_bridge_serves(self):
        context = self._check_bridge_files_added(self._simulator("nvc"))
        self.assertEqual(sorted(context.hooks), ["ghdl", "modelsim", "nvc"])
        self.assertIsNotNone(context.hooks["nvc"]["run_flags"])
        self.assertIsNotNone(context.hooks["ghdl"]["elab_flags"])
        self.assertIsNotNone(context.hooks["ghdl"]["run_env"])
        self.assertIsNotNone(context.hooks["modelsim"]["process_flags"])
        # Questa finds the library by the absolute path in its FLI attributes
        self.assertIsNone(context.hooks["modelsim"]["run_env"])

    def test_bridge_setup_failure_is_reported(self):
        context = self._context(self._simulator("nvc"))
        with mock.patch(
            "vunit_python_bridge.bridge.setup",
            side_effect=native_library.PythonBridgeError("no compiler"),
        ), mock.patch("vunit_python_bridge.LOGGER") as logger:
            with self.assertRaises(SystemExit):
                vunit_python_bridge.setup(context)
        logger.error.assert_called_once_with("%s", mock.ANY)

    def test_importing_the_package_has_no_side_effects(self):
        # Re-importing must not create any files or directories or run any subprocess.
        def listing():
            return sorted(
                str(path) for path in native_library.PACKAGE_PATH.rglob("*") if "__pycache__" not in str(path)
            )

        before = listing()
        with mock.patch("subprocess.run") as run_mock:
            import importlib

            for module in (native_library, bridge_setup, simulator_hooks, vunit_python_bridge):
                importlib.reload(module)
        run_mock.assert_not_called()
        self.assertEqual(listing(), before)


class TestBridgePackageSubstitution(unittest.TestCase):
    """
    Library token substitution into the generated python_bridge_pkg.vhd.
    """

    def setUp(self):
        self.tempdir_cm = create_tempdir()
        self.tempdir = self.tempdir_cm.__enter__()
        self.addCleanup(self.tempdir_cm.__exit__, None, None, None)
        self.run_script = _write_run_script(self.tempdir / "run.py")

    def _setup(self, simulator_name, backend=None, library_file_name="libvunit_python_bridge.so"):
        fake_library_file = self.tempdir / "cache" / library_file_name
        with mock.patch("vunit_python_bridge.bridge.prepare_library", return_value=fake_library_file):
            return bridge_setup.setup(self.tempdir / "out", self.run_script, simulator_name, "/sim/bin", backend)

    def _fli_setup(self):
        return self._setup("modelsim", library_file_name="libvunit_python_bridge_fli.so")

    def _ffi_text(self, bridge):
        for path in bridge.vhdl_files:
            if path.name == "python_bridge_pkg.vhd":
                return path.read_text(encoding="utf-8")
        self.fail("python_bridge_pkg.vhd not found among bridge.vhdl_files")
        return ""

    def test_generated_package_is_the_private_bridge_package(self):
        text = self._ffi_text(self._setup("nvc"))
        self.assertIn("package python_bridge_pkg is", text)
        self.assertIn("package body python_bridge_pkg is", text)

    def test_exports_match_the_native_library(self):
        text = self._ffi_text(self._setup("nvc"))
        declared = set(re.findall(r'VHPIDIRECT \S+ (\w+)"', text))
        self.assertEqual(declared, set(EXPECTED_EXPORTS))

    def test_token_is_library_file_name_for_nvc(self):
        bridge = self._setup("nvc")
        text = self._ffi_text(bridge)
        self.assertIn('"VHPIDIRECT libvunit_python_bridge.so vpy_begin"', text)

    def test_token_is_library_file_name_for_ghdl_mcode(self):
        bridge = self._setup("ghdl", backend="mcode")
        text = self._ffi_text(bridge)
        self.assertIn('"VHPIDIRECT libvunit_python_bridge.so vpy_begin"', text)

    def test_token_is_library_file_name_for_ghdl_llvm_jit(self):
        bridge = self._setup("ghdl", backend="llvm-jit")
        text = self._ffi_text(bridge)
        self.assertIn('"VHPIDIRECT libvunit_python_bridge.so vpy_begin"', text)

    def test_token_is_link_flag_for_ghdl_llvm(self):
        bridge = self._setup("ghdl", backend="llvm")
        text = self._ffi_text(bridge)
        self.assertIn('"VHPIDIRECT -lvunit_python_bridge vpy_begin"', text)

    def test_token_is_link_flag_for_ghdl_gcc(self):
        bridge = self._setup("ghdl", backend="gcc")
        text = self._ffi_text(bridge)
        self.assertIn('"VHPIDIRECT -lvunit_python_bridge vpy_begin"', text)

    def test_no_remaining_placeholder(self):
        for bridge in (self._setup("nvc"), self._fli_setup()):
            text = self._ffi_text(bridge)
            self.assertNotIn("{library}", text)
            self.assertNotIn("{foreign:vpy_", text)

    def test_fli_attributes_name_the_wrapper_and_the_library_path(self):
        # Questa resolves the absolute path, so the library stays in the cache.
        bridge = self._fli_setup()
        text = self._ffi_text(bridge)
        self.assertIn(f'"fli_vpy_begin {bridge.library_file!s}"', text)
        self.assertIn(f'"fli_vpy_result_read_reals {bridge.library_file!s}"', text)
        attributes = [line for line in text.splitlines() if "attribute foreign" in line]
        self.assertEqual([line for line in attributes if "VHPIDIRECT" in line or "{foreign:" in line], [])

    def test_fli_attributes_cover_every_entry_point(self):
        bridge = self._fli_setup()
        text = self._ffi_text(bridge)
        declared = set(re.findall(r'"fli_(\w+) \S+"', text))
        self.assertEqual(declared, set(EXPECTED_EXPORTS))

    def test_fli_library_is_the_fli_variant(self):
        with mock.patch("vunit_python_bridge.bridge.prepare_library") as prepare_mock:
            prepare_mock.return_value = self.tempdir / "cache" / "libvunit_python_bridge_fli.so"
            bridge_setup.setup(self.tempdir / "out", self.run_script, "modelsim", "/sim/bin")
        # The simulator prefix selects the FLI variant of the library.
        self.assertEqual(prepare_mock.call_args.args[1], Path("/sim/bin"))

    def test_fli_without_a_simulator_prefix_raises(self):
        # The FLI variant is built against the simulator installation, so there has to be one.
        with self.assertRaisesRegex(RuntimeError, "it was not found"):
            bridge_setup.setup(self.tempdir / "out", self.run_script, "modelsim", None)

    def test_no_simulator_prefix_for_vhpidirect(self):
        with mock.patch("vunit_python_bridge.bridge.prepare_library") as prepare_mock:
            prepare_mock.return_value = self.tempdir / "cache" / "libvunit_python_bridge.so"
            bridge_setup.setup(self.tempdir / "out", self.run_script, "nvc", "/sim/bin")
        self.assertIsNone(prepare_mock.call_args.args[1])

    def test_unsupported_simulator_raises(self):
        with self.assertRaisesRegex(RuntimeError, "NVC, GHDL or Questa/ModelSim"):
            self._setup("rivierapro")

    def test_all_vhpidirect_tokens_fit_ghdl_limit(self):
        for simulator_name, backend in (
            ("nvc", None),
            ("ghdl", "mcode"),
            ("ghdl", "llvm"),
            ("ghdl", "gcc"),
        ):
            bridge = self._setup(simulator_name, backend)
            text = self._ffi_text(bridge)
            tokens = re.findall(r'VHPIDIRECT\s+(\S+)\s+\S+"', text)
            self.assertTrue(tokens, "no VHPIDIRECT tokens found")
            for token in tokens:
                self.assertLessEqual(len(token), 32, f"token {token!r} exceeds GHDL's 32 character limit")
                self.assertNotIn(" ", token)


@unittest.skipIf(sys.platform == "win32", "POSIX build/cache behavior")
class TestPosixBuildAndCache(unittest.TestCase):
    """
    Compilation and caching of the native bridge library on Linux/macOS.

    Only a couple of real compiles happen here (gcc + Python headers are
    available in this environment); everything else is asserted not to compile.
    """

    def setUp(self):
        self.tempdir_cm = create_tempdir()
        self.tempdir = self.tempdir_cm.__enter__()
        self.addCleanup(self.tempdir_cm.__exit__, None, None, None)
        self.run_script = _write_run_script(self.tempdir / "run.py")

    def _setup(self, output_path=None):
        return bridge_setup.setup(output_path or self.tempdir / "out", self.run_script)

    def test_first_setup_compiles_and_names_library(self):
        bridge = self._setup()
        self.assertTrue(bridge.library_file.is_file())
        self.assertEqual(bridge.library_file.name, "libvunit_python_bridge.so")

    def test_second_setup_reuses_cache_without_compiling(self):
        self._setup()
        with mock.patch("subprocess.run") as run_mock:
            bridge = self._setup()
        run_mock.assert_not_called()
        self.assertTrue(bridge.library_file.is_file())

    def test_changed_source_gets_new_cache_dir_and_recompiles(self):
        first = self._setup()

        modified_native = self.tempdir / "native"
        shutil.copytree(native_library.NATIVE_PATH, modified_native)
        with (modified_native / "error.c").open("a", encoding="utf-8") as fptr:
            fptr.write("\n/* test tweak */\n")

        with mock.patch("vunit_python_bridge.native_library.NATIVE_PATH", modified_native):
            second = self._setup()

        self.assertNotEqual(first.library_file.parent, second.library_file.parent)
        self.assertTrue(second.library_file.is_file())

    def test_compile_failure_raises_with_compiler_output(self):
        fake_proc = mock.Mock(returncode=1, stdout=b"bogus.c:1:1: error: fake failure\n")
        with mock.patch("subprocess.run", return_value=fake_proc):
            with self.assertRaisesRegex(RuntimeError, "fake failure"):
                self._setup()

    def test_missing_python_h_raises_actionable_error(self):
        empty_include_dir = self.tempdir / "no_headers"
        empty_include_dir.mkdir()
        real_get_paths = native_library.sysconfig.get_paths

        def fake_get_paths():
            paths = dict(real_get_paths())
            paths["include"] = str(empty_include_dir)
            paths["platinclude"] = str(empty_include_dir)
            return paths

        with mock.patch("vunit_python_bridge.native_library.sysconfig.get_paths", side_effect=fake_get_paths):
            with self.assertRaisesRegex(RuntimeError, "Python.h"):
                self._setup()

    def test_static_only_python_raises(self):
        real_get_config_var = native_library.sysconfig.get_config_var

        def fake_get_config_var(name):
            if name == "Py_ENABLE_SHARED":
                return 0
            return real_get_config_var(name)

        with mock.patch("vunit_python_bridge.native_library.sysconfig.get_config_var", side_effect=fake_get_config_var):
            with self.assertRaisesRegex(RuntimeError, "shared Python library"):
                self._setup()

    def test_free_threaded_python_raises(self):
        real_get_config_var = native_library.sysconfig.get_config_var

        def fake_get_config_var(name):
            if name == "Py_GIL_DISABLED":
                return 1
            return real_get_config_var(name)

        with mock.patch("vunit_python_bridge.native_library.sysconfig.get_config_var", side_effect=fake_get_config_var):
            with self.assertRaisesRegex(RuntimeError, "free-threaded"):
                self._setup()

    def test_library_exports_exactly_the_contract(self):
        nm = shutil.which("nm")
        if nm is None:
            self.skipTest("nm is not available")
        bridge = self._setup()
        proc = subprocess.run(
            [nm, "-D", "--defined-only", str(bridge.library_file)],
            check=True,
            capture_output=True,
            text=True,
        )
        exported = set()
        for line in proc.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[-2] in "TtWwDdBb":
                exported.add(fields[-1])
        # -fvisibility=hidden plus VPY_EXPORT: only the contract is exported,
        # no bridge internals (vpy_initialize, vpy_set_error, ...) leak out.
        self.assertEqual(exported, set(EXPECTED_EXPORTS))

    def _fake_simulator_prefix(self):
        """
        A simulator installation with just the FLI header the build needs.
        """
        include = self.tempdir / "questa" / "include"
        include.mkdir(parents=True)
        (include / "mti.h").write_text("/* fake */\n", encoding="utf-8")
        prefix = self.tempdir / "questa" / "bin"
        prefix.mkdir()
        return prefix

    @staticmethod
    def _compiler_stub(calls):
        """
        Stand in for the C compiler: record the command and create its output.
        """

        def run(cmd, **kwargs):  # pylint: disable=unused-argument
            calls.append(cmd)
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"")
            return mock.Mock(returncode=0, stdout=b"")

        return run

    def test_fli_variant_adds_the_front_end_and_the_simulator_headers(self):
        prefix = self._fake_simulator_prefix()
        calls = []
        with mock.patch("subprocess.run", side_effect=self._compiler_stub(calls)):
            library_file = native_library.prepare_library(self.tempdir / "out", prefix)
        self.assertEqual(len(calls), 1)
        self.assertEqual(library_file.name, "libvunit_python_bridge_fli.so")
        self.assertIn(str(native_library.NATIVE_PATH / "fli.c"), calls[0])
        self.assertIn(f"-I{prefix.parent / 'include'!s}", calls[0])

    def test_vhpidirect_variant_omits_the_front_end(self):
        calls = []
        with mock.patch("subprocess.run", side_effect=self._compiler_stub(calls)):
            library_file = native_library.prepare_library(self.tempdir / "out")
        self.assertEqual(library_file.name, "libvunit_python_bridge.so")
        self.assertNotIn(str(native_library.NATIVE_PATH / "fli.c"), calls[0])

    def test_fli_and_vhpidirect_variants_are_cached_separately(self):
        prefix = self._fake_simulator_prefix()
        calls = []
        with mock.patch("subprocess.run", side_effect=self._compiler_stub(calls)):
            vhpidirect = native_library.prepare_library(self.tempdir / "out")
            fli = native_library.prepare_library(self.tempdir / "out", prefix)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(fli.parent, vhpidirect.parent)

    def test_second_fli_setup_reuses_cache_without_compiling(self):
        prefix = self._fake_simulator_prefix()
        with mock.patch("subprocess.run", side_effect=self._compiler_stub([])):
            first = native_library.prepare_library(self.tempdir / "out", prefix)
        with mock.patch("subprocess.run") as run_mock:
            second = native_library.prepare_library(self.tempdir / "out", prefix)
        run_mock.assert_not_called()
        self.assertEqual(first, second)

    def test_another_simulator_installation_gets_its_own_cache_dir(self):
        first_prefix = self._fake_simulator_prefix()
        other = self.tempdir / "other_questa"
        (other / "include").mkdir(parents=True)
        (other / "include" / "mti.h").write_text("/* fake */\n", encoding="utf-8")
        (other / "bin").mkdir()
        calls = []
        with mock.patch("subprocess.run", side_effect=self._compiler_stub(calls)):
            first = native_library.prepare_library(self.tempdir / "out", first_prefix)
            second = native_library.prepare_library(self.tempdir / "out", other / "bin")
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(first.parent, second.parent)

    def test_missing_mti_h_raises_actionable_error(self):
        prefix = self.tempdir / "questa" / "bin"
        prefix.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "mti.h"):
            native_library.prepare_library(self.tempdir / "out", prefix)

    def test_no_prebuilt_library_in_repository(self):
        # Linux libraries are built on first use and Windows DLLs are added to releases by CI
        matches = []
        for pattern in ["*.so", "*.dll"]:
            matches += glob(str(native_library.PACKAGE_PATH / "**" / pattern), recursive=True)
        self.assertEqual(matches, [])


class TestConfigFile(unittest.TestCase):
    """
    _config_text / _write_if_changed
    """

    def test_config_keys_linux(self):
        with mock.patch("sys.platform", "linux"):
            text = bridge_setup._config_text("/run/script/dir")  # pylint: disable=protected-access
        keys = dict(line.split("=", 1) for line in text.splitlines())
        self.assertEqual(set(keys), {"executable", "prefix", "runtime", "run_script_dir"})
        self.assertEqual(keys["executable"], sys.executable)
        self.assertEqual(keys["prefix"], sys.prefix)
        self.assertEqual(keys["runtime"], str(bridge_setup.RUNTIME_SOURCE))
        self.assertEqual(keys["run_script_dir"], "/run/script/dir")

    def test_config_keys_windows_include_python_dll(self):
        with (
            mock.patch("sys.platform", "win32"),
            mock.patch("vunit_python_bridge.bridge.windows_python_dll", return_value=r"C:\python.dll"),
        ):
            text = bridge_setup._config_text("/run/script/dir")  # pylint: disable=protected-access
        keys = dict(line.split("=", 1) for line in text.splitlines())
        self.assertEqual(keys["python_dll"], r"C:\python.dll")

    def test_write_if_changed_does_not_rewrite_identical_content(self):
        with create_tempdir() as tempdir:
            path = tempdir / "file.txt"
            bridge_setup._write_if_changed(path, "hello")  # pylint: disable=protected-access
            mtime_before = path.stat().st_mtime_ns
            bridge_setup._write_if_changed(path, "hello")  # pylint: disable=protected-access
            self.assertEqual(path.stat().st_mtime_ns, mtime_before)

    def test_write_if_changed_rewrites_changed_content(self):
        with create_tempdir() as tempdir:
            path = tempdir / "file.txt"
            bridge_setup._write_if_changed(path, "hello")  # pylint: disable=protected-access
            bridge_setup._write_if_changed(path, "world")  # pylint: disable=protected-access
            self.assertEqual(path.read_text(encoding="utf-8"), "world")

    def test_run_script_dir_is_the_directory_of_the_run_script(self):
        with create_tempdir() as tempdir:
            run_script = _write_run_script(tempdir / "run.py")
            fake_library_file = tempdir / "cache" / "libvunit_python_bridge.so"
            with mock.patch("vunit_python_bridge.bridge.prepare_library", return_value=fake_library_file):
                bridge_setup.setup(tempdir / "out", run_script)
            config = (fake_library_file.parent / bridge_setup.CONFIG_FILE_NAME).read_text(encoding="utf-8")
            keys = dict(line.split("=", 1) for line in config.splitlines())
            self.assertEqual(keys["run_script_dir"], str(tempdir.resolve()))

    def test_config_paths_with_spaces_and_unicode_written_as_utf8(self):
        with create_tempdir() as tempdir:
            weird_dir = tempdir / "weird dir \u00e5\u00e4\u00f6 \u65e5\u672c\u8a9e"
            weird_dir.mkdir()
            with mock.patch("sys.platform", "linux"):
                text = bridge_setup._config_text(str(weird_dir))  # pylint: disable=protected-access
            self.assertIn(str(weird_dir), text)
            path = tempdir / "cfg"
            bridge_setup._write_if_changed(path, text)  # pylint: disable=protected-access
            self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_line_break_in_path_raises(self):
        with mock.patch("sys.executable", "/usr/bin/py\nthon"):
            with self.assertRaisesRegex(RuntimeError, "line breaks"):
                bridge_setup._config_text("/run/script/dir")  # pylint: disable=protected-access


class TestWindowsDllSelection(unittest.TestCase):
    """
    Windows prebuilt-DLL selection logic. Testable on any platform since it
    is pure logic + file copying, gated only by explicit patches here (never
    by sys.platform inside these helper functions themselves).
    """

    def test_windows_dll_name_for_supported_versions(self):
        for minor in range(10, 15):
            self.assertEqual(
                native_library.windows_dll_name((3, minor)),
                f"vunit_python_bridge-cp3{minor}-win_amd64.dll",
            )

    def _prepare(self, tempdir, dll_bytes, version_info=(3, 12)):
        binary_path = tempdir / "bin"
        binary_path.mkdir(exist_ok=True)
        name = native_library.windows_dll_name(version_info)
        (binary_path / name).write_bytes(dll_bytes)
        root = tempdir / "root"
        with (
            mock.patch("vunit_python_bridge.native_library.BINARY_PATH", binary_path),
            mock.patch("sys.version_info", version_info),
            mock.patch("vunit_python_bridge.native_library.sysconfig.get_platform", return_value="win-amd64"),
            mock.patch("subprocess.run") as run_mock,
            mock.patch("shutil.which") as which_mock,
        ):
            target = native_library._prepare_windows_library(root)  # pylint: disable=protected-access
        run_mock.assert_not_called()
        which_mock.assert_not_called()
        return target

    def test_copies_selected_dll_as_vunit_python_bridge_dll(self):
        with create_tempdir() as tempdir:
            target = self._prepare(tempdir, b"fake-dll-content")
            self.assertEqual(target.name, "vunit_python_bridge.dll")
            self.assertEqual(target.read_bytes(), b"fake-dll-content")

    def test_reuses_existing_file_when_content_unchanged(self):
        with create_tempdir() as tempdir:
            first = self._prepare(tempdir, b"same-content")
            mtime_before = first.stat().st_mtime_ns
            second = self._prepare(tempdir, b"same-content")
            self.assertEqual(first, second)
            self.assertEqual(second.stat().st_mtime_ns, mtime_before)

    def test_new_directory_when_content_changes(self):
        with create_tempdir() as tempdir:
            first = self._prepare(tempdir, b"version-one")
            second = self._prepare(tempdir, b"version-two")
            self.assertNotEqual(first.parent, second.parent)

    def test_missing_dll_for_running_version_raises_actionable_error(self):
        root = None
        with create_tempdir() as tempdir:
            binary_path = tempdir / "bin"
            binary_path.mkdir()
            root = tempdir / "root"
            with (
                mock.patch("vunit_python_bridge.native_library.BINARY_PATH", binary_path),
                mock.patch("sys.version_info", (3, 12)),
                mock.patch("vunit_python_bridge.native_library.sysconfig.get_platform", return_value="win-amd64"),
                mock.patch("subprocess.run") as run_mock,
            ):
                with self.assertRaisesRegex(RuntimeError, "No prebuilt Python bridge DLL"):
                    native_library._prepare_windows_library(root)  # pylint: disable=protected-access
            run_mock.assert_not_called()

    def test_non_win_amd64_platform_raises(self):
        with mock.patch("vunit_python_bridge.native_library.sysconfig.get_platform", return_value="mingw"):
            with self.assertRaisesRegex(RuntimeError, "64-bit"):
                native_library._prepare_windows_library(Path("root"))  # pylint: disable=protected-access


class TestSimulatorHooks(unittest.TestCase):
    """
    The hooks registered with the package context: what NVC, GHDL and Questa/ModelSim
    are given for a simulation of the project.
    """

    def _hooks(self, library_file):
        bridge = bridge_setup.PythonBridge(library_file=library_file, vhdl_files=[])
        context = _FakeContext(None, Path("/out"), Path("/run.py"))
        simulator_hooks.register(context, bridge)
        return context.hooks

    @staticmethod
    def _ghdl(backend):
        """
        A GHDL interface as a hook gets it: it knows its own backend.
        """
        simulator = mock.Mock()
        simulator.backend = backend
        return simulator

    @staticmethod
    def _questa(prefix="/questa/bin", help_output=f"{simulator_hooks.NO_AUTO_LD_LIBRARY_PATH} Disable it"):
        """
        A Questa/ModelSim interface and the vsim help output the hook asks it for.
        """
        simulator = mock.Mock()
        simulator.prefix = prefix
        simulator.get_env.return_value = None
        return simulator, mock.patch(
            "vunit_python_bridge.simulator_hooks.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout=help_output, stderr=""),
        )

    def test_nvc_loads_the_library_at_run_time(self):
        library_file = Path("/some/dir/libvunit_python_bridge.so")
        hooks = self._hooks(library_file)
        self.assertEqual(hooks["nvc"]["run_flags"](mock.Mock()), [f"--load={library_file!s}"])
        # NVC dlopen()s the library itself, nothing to do at elaboration
        self.assertIsNone(hooks["nvc"]["elab_flags"])

    def test_ghdl_elab_flags_empty_for_mcode_and_jit(self):
        hooks = self._hooks(Path("/some/dir/libvunit_python_bridge.so"))
        for backend in ("mcode", "llvm-jit"):
            self.assertEqual(hooks["ghdl"]["elab_flags"](self._ghdl(backend)), [], backend)

    def test_ghdl_elab_flags_for_linking_backends(self):
        bridge_dir = Path("/some/dir")
        hooks = self._hooks(bridge_dir / "libvunit_python_bridge.so")
        for backend in ("llvm", "gcc"):
            self.assertEqual(hooks["ghdl"]["elab_flags"](self._ghdl(backend)), [f"-Wl,-L{bridge_dir!s}"], backend)

    def test_ghdl_run_env_prepends_ld_library_path_without_mutating_input(self):
        bridge_dir = Path("/some/dir")
        hooks = self._hooks(bridge_dir / "libvunit_python_bridge.so")
        env = {"LD_LIBRARY_PATH": "/existing/path"}
        with mock.patch("vunit_python_bridge.simulator_hooks.sys.platform", "linux"):
            result = hooks["ghdl"]["run_env"](mock.Mock(), env)
        self.assertEqual(result["LD_LIBRARY_PATH"], str(bridge_dir) + os.pathsep + "/existing/path")
        # Input must not be mutated.
        self.assertEqual(env, {"LD_LIBRARY_PATH": "/existing/path"})
        self.assertIsNot(result, env)

    def test_ghdl_run_env_uses_dyld_library_path_on_macos(self):
        bridge_dir = Path("/some/dir")
        hooks = self._hooks(bridge_dir / "libvunit_python_bridge.so")
        with mock.patch("vunit_python_bridge.simulator_hooks.sys.platform", "darwin"):
            result = hooks["ghdl"]["run_env"](mock.Mock(), {})
        self.assertEqual(result["DYLD_LIBRARY_PATH"], str(bridge_dir))

    def test_ghdl_run_env_uses_path_variable_on_windows(self):
        bridge_dir = Path("/some/dir")
        hooks = self._hooks(bridge_dir / "vunit_python_bridge.dll")
        with mock.patch("vunit_python_bridge.simulator_hooks.sys.platform", "win32"):
            result = hooks["ghdl"]["run_env"](mock.Mock(), {})
        self.assertEqual(result["PATH"], str(bridge_dir))
        self.assertNotIn("LD_LIBRARY_PATH", result)

    def test_modelsim_gets_no_run_flags(self):
        # -noautoldlibpath is only honoured on the command line of the vsim process
        # VUnit starts, which is what process_flags extends.
        hooks = self._hooks(Path("/some/dir/libvunit_python_bridge_fli.so"))
        self.assertIsNone(hooks["modelsim"]["run_flags"])
        self.assertIsNone(hooks["modelsim"]["elab_flags"])

    def test_modelsim_process_flags_disable_the_bundled_cxx_runtime_on_linux(self):
        hooks = self._hooks(Path("/some/dir/libvunit_python_bridge_fli.so"))
        simulator, help_patch = self._questa()
        with mock.patch("vunit_python_bridge.simulator_hooks.sys.platform", "linux"), help_patch as run:
            self.assertEqual(hooks["modelsim"]["process_flags"](simulator), ["-noautoldlibpath"])
            # The answer of an installation is remembered, vsim is only asked once.
            self.assertEqual(hooks["modelsim"]["process_flags"](simulator), ["-noautoldlibpath"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args[0][0][0], str(Path("/questa/bin/vsim")))

    def test_modelsim_process_flags_empty_when_vsim_does_not_know_the_flag(self):
        hooks = self._hooks(Path("/some/dir/libvunit_python_bridge_fli.so"))
        simulator, help_patch = self._questa(help_output="-nothing -of -interest")
        with mock.patch("vunit_python_bridge.simulator_hooks.sys.platform", "linux"), help_patch:
            self.assertEqual(hooks["modelsim"]["process_flags"](simulator), [])

    def test_modelsim_process_flags_kept_when_vsim_cannot_be_asked(self):
        hooks = self._hooks(Path("/some/dir/libvunit_python_bridge_fli.so"))
        simulator, _ = self._questa()
        no_vsim = mock.patch("vunit_python_bridge.simulator_hooks.subprocess.run", side_effect=OSError("no vsim"))
        with mock.patch("vunit_python_bridge.simulator_hooks.sys.platform", "linux"), no_vsim:
            self.assertEqual(hooks["modelsim"]["process_flags"](simulator), ["-noautoldlibpath"])

    def test_modelsim_process_flags_empty_on_windows(self):
        hooks = self._hooks(Path("/some/dir/vunit_python_bridge_fli.dll"))
        simulator, help_patch = self._questa()
        with mock.patch("vunit_python_bridge.simulator_hooks.sys.platform", "win32"), help_patch as run:
            self.assertEqual(hooks["modelsim"]["process_flags"](simulator), [])
        run.assert_not_called()


class TestForeignApplicationBuild(unittest.TestCase):
    """
    The VHPI application is built under the output path once and rebuilt when its inputs change.
    """

    def test_builds_once_and_rebuilds_when_the_fingerprint_changes(self):
        with create_tempdir() as tempdir:
            output_path = Path(tempdir) / "out"
            prefix = str(Path(tempdir) / "rivierapro" / "bin")
            target = output_path / "rivierapro" / "libraries" / "python.dll"

            def fake_build(target, sources, simulator_prefix):  # pylint: disable=unused-argument
                target.write_text("built", encoding="utf-8")

            with mock.patch.object(foreign_application, "_build_vhpi", side_effect=fake_build) as build:
                foreign_application.setup_vhpi_application(output_path, "rivierapro", prefix)
                foreign_application.setup_vhpi_application(output_path, "rivierapro", prefix)
            self.assertEqual(build.call_count, 1)
            self.assertTrue(target.exists())
            self.assertTrue(target.with_suffix(".dll.fingerprint").exists())

            # Another simulator installation changes the fingerprint
            other = str(Path(tempdir) / "other" / "bin")
            with mock.patch.object(foreign_application, "_build_vhpi", side_effect=fake_build) as build:
                foreign_application.setup_vhpi_application(output_path, "rivierapro", other)
            self.assertEqual(build.call_count, 1)

            # A missing library is rebuilt even with a matching fingerprint
            target.unlink()
            with mock.patch.object(foreign_application, "_build_vhpi", side_effect=fake_build) as build:
                foreign_application.setup_vhpi_application(output_path, "rivierapro", other)
            self.assertEqual(build.call_count, 1)

    def test_failed_build_leaves_no_fingerprint(self):
        with create_tempdir() as tempdir:
            output_path = Path(tempdir) / "out"
            prefix = str(Path(tempdir) / "rivierapro" / "bin")
            with mock.patch.object(foreign_application, "_build_vhpi", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    foreign_application.setup_vhpi_application(output_path, "rivierapro", prefix)
            self.assertFalse(list((output_path / "rivierapro" / "libraries").glob("*.fingerprint")))

    def test_a_missing_simulator_installation_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "it was not found"):
            foreign_application.setup_vhpi_application(Path("/out"), "rivierapro", None)


if __name__ == "__main__":
    unittest.main()

