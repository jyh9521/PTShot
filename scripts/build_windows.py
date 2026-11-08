"""Convenience entry point for the Material 3 Expressive Windows package."""
import shutil
import subprocess
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    subprocess.run([shutil.which("npm.cmd") or "npm.cmd", "run", "package:win"], cwd=root, check=True)
