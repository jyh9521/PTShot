"""Launch the local Material 3 Expressive desktop application."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .core import ShotError
from .tools import app_root


def launch() -> None:
    root = app_root()
    packaged = root / "dist" / "PTShot-M3E" / "PTShot.exe"
    if packaged.is_file():
        subprocess.Popen([str(packaged)], cwd=packaged.parent)
        return
    electron = root / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
    if not electron.is_file():
        raise ShotError("请先执行 npm ci 和 python scripts/prepare_electron.py，或启动打包版 PTShot.exe")
    if not (root / "frontend-dist" / "index.html").exists():
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm:
            raise ShotError("请先安装 Node.js 24 并执行 npm run build")
        subprocess.run([npm, "run", "build"], cwd=root, check=True)
    subprocess.Popen([str(electron), str(root)], cwd=root)
