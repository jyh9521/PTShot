import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ptshot.core import Cancelled, ShotError
from ptshot.tools import Runner, atomic_binary, discover_tools, environment


class ToolsTests(unittest.TestCase):
    def test_local_over_path_and_explicit_over_local(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            local = root / "tools" / "bin" / ("oxipng.exe" if os.name == "nt" else "oxipng")
            local.parent.mkdir(parents=True)
            local.write_bytes(b"fixture")
            custom = root / "custom-oxi.exe"
            custom.write_bytes(b"fixture")
            self.assertEqual(discover_tools(root)["oxipng"], str(local.resolve()))
            self.assertEqual(discover_tools(root, {"oxipng": str(custom)})["oxipng"], str(custom.resolve()))
            self.assertNotIn("oxipng", discover_tools(root, {"oxipng": str(root / "missing.exe")}))

    def test_env_prepends_tool_dirs_and_isolates_mosaic_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "tools" / "mosaic-cli.toml"
            config.parent.mkdir()
            config.write_text("")
            result = environment({"mosaic-cli": str(root / "mosaic-cli.exe")}, root)
            self.assertTrue(result["PATH"].startswith(str(root)))
            self.assertEqual(result["MOSAIC_CLI_CONFIG"], str(config.resolve()))

    def test_atomic_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bin" / "tool.exe"
            atomic_binary(path, b"one")
            atomic_binary(path, b"two")
            self.assertEqual(path.read_bytes(), b"two")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_runner_propagates_exit_status(self):
        import sys
        runner = Runner(threading.Event(), lambda _: None, os.environ.copy())
        self.assertEqual(runner.run([sys.executable, "-c", "print('ok')"]).strip(), "ok")
        with self.assertRaises(ShotError):
            runner.run([sys.executable, "-c", "raise SystemExit(7)"])

    def test_runner_cancelled_before_spawn(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(Cancelled), patch("subprocess.Popen") as popen:
            Runner(stop, lambda _: None, {}).run(["unused"])
        popen.assert_not_called()

    def test_runner_timeout_kills_process(self):
        import sys
        runner = Runner(threading.Event(), lambda _: None, os.environ.copy())
        with self.assertRaises(ShotError):
            runner.run([sys.executable, "-c", "import time;time.sleep(30)"], timeout=0.1)
