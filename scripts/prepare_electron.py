"""Install the official Electron ZIP, verifying the checksum shipped in its npm package."""
import hashlib
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    base = ROOT / "node_modules" / "electron"
    version = json.loads((base / "package.json").read_text())["version"]
    name = f"electron-v{version}-win32-x64.zip"
    checksums = json.loads((base / "checksums.json").read_text())
    expected = checksums[name]
    archive = ROOT / "build" / "downloads" / name
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        request = urllib.request.Request(f"https://api.github.com/repos/electron/electron/releases/tags/v{version}",
                                         headers={"User-Agent": "PTShot-build"})
        release = json.load(urllib.request.urlopen(request, timeout=45))
        asset = next(item for item in release["assets"] if item["name"] == name)
        request = urllib.request.Request(asset["url"], headers={"User-Agent": "PTShot-build", "Accept": "application/octet-stream"})
        with urllib.request.urlopen(request, timeout=90) as response, archive.open("wb") as target:
            while block := response.read(1024 * 1024):
                target.write(block)
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected, "Electron checksum mismatch"
    destination = (base / "dist").resolve()
    assert destination.is_relative_to(ROOT.resolve())
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        assert all((destination / member).resolve().is_relative_to(destination) for member in bundle.namelist())
        bundle.extractall(destination)
    (base / "path.txt").write_text("electron.exe", encoding="utf-8")
    print(f"ELECTRON={version} SHA256={expected} VERIFIED")


if __name__ == "__main__":
    main()
