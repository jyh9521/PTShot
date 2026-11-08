"""Freeze only the Python worker; the Material UI is packaged by Electron."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    if os.name != "nt":
        raise SystemExit("Build on Windows x64")
    destination = (ROOT / "build" / "desktop-worker").resolve()
    assert destination.is_relative_to((ROOT / "build").resolve())
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--console",
        "--name", "PTShotWorker", "--add-data", str(ROOT / "dependencies.lock.json") + ";.",
        "--add-data", str(ROOT / "tools" / "mosaic-cli.toml") + ";tools", "--distpath", str(destination),
        "--workpath", str(ROOT / "build" / "worker-pyinstaller"),
        "--specpath", str(ROOT / "build"), "worker.py"], cwd=ROOT, check=True)
    print("WORKER BUILD PASS")


if __name__ == "__main__":
    main()
