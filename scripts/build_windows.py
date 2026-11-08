"""Build a Windows x64 onedir application and a self-contained portable ZIP."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ptshot.core import atomic_text
from ptshot.tools import TOOL_NAMES, discover_tools


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if os.name != "nt":
        raise SystemExit("Build this package on Windows x64")
    tools = discover_tools(ROOT)
    assert len(tools) == len(TOOL_NAMES), tools
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "PTShot", "--add-data", "dependencies.lock.json;.", "--add-data", "tools/mosaic-cli.toml;tools",
        "--distpath", "dist", "--workpath", "build/pyinstaller", "run.py"], cwd=ROOT, check=True)
    destination = ROOT / "dist" / "PTShot"
    native = destination / "tools" / "bin"
    native.mkdir(parents=True, exist_ok=True)
    inventory = {}
    for name, source in tools.items():
        path = Path(source)
        target = native / (name + ".exe")
        shutil.copy2(path, target)
        args = [str(path), "--Version" if name == "mediainfo" else "-version" if name in ("ffmpeg", "ffprobe") else "--version"]
        result = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace")
        assert result.returncode == 0, result.stderr
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        inventory[name] = {"version": result.stdout.splitlines()[:2], "sha256": digest, "bytes": target.stat().st_size}
    for dll in (ROOT / "tools" / "bin").glob("*.dll"):
        shutil.copy2(dll, native / dll.name)
    shutil.copytree(ROOT / "tools" / "licenses", destination / "tools" / "licenses", dirs_exist_ok=True)
    ffmpeg_root = Path(tools["ffmpeg"]).parent.parent
    for name in ("LICENSE", "README.txt"):
        source = ffmpeg_root / name
        if source.exists():
            target = destination / "tools" / "licenses" / "ffmpeg" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for name in ("README.md", "THIRD_PARTY.md", "dependencies.lock.json"):
        shutil.copy2(ROOT / name, destination / name)
    shutil.copy2(ROOT / "tools" / "mosaic-cli.toml", destination / "tools" / "mosaic-cli.toml")
    atomic_text(destination / "BUNDLED_TOOLS.json", json.dumps(inventory, ensure_ascii=False, indent=2))
    # Keep the portable archive deterministic for the same input tree (file timestamps normalized).
    archive = ROOT / "dist" / "PTShot-Windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(destination.rglob("*")):
            if path.is_file() and not path.is_relative_to(destination / "output"):
                relative = path.relative_to(destination.parent).as_posix()
                info = zipfile.ZipInfo(relative, date_time=(2026, 11, 8, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                with path.open("rb") as source, bundle.open(info, "w", force_zip64=True) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert "PTShot/PTShot.exe" in bundle.namelist()
        assert all("PTShot/tools/bin/" + name + ".exe" in bundle.namelist() for name in TOOL_NAMES)
    print(f"EXE={destination / 'PTShot.exe'}")
    print(f"ZIP={archive}")
    print(f"ZIP_BYTES={archive.stat().st_size}")
    print("BUILD PASS")


if __name__ == "__main__":
    main()
