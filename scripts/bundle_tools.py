"""Copy discovered native tools with their hashes and license notices into a package."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ptshot.tools import discover_tools


def main():
    destination = Path(sys.argv[1]).resolve()
    assert destination.is_relative_to((ROOT / "dist").resolve())
    native = destination / "tools" / "bin"
    native.mkdir(parents=True, exist_ok=True)
    found = discover_tools(ROOT)
    assert len(found) == 5, found
    inventory = {}
    for name, source in found.items():
        target = native / (name + ".exe")
        shutil.copy2(source, target)
        flag = "--Version" if name == "mediainfo" else "-version" if name in ("ffmpeg", "ffprobe") else "--version"
        result = subprocess.run([source, flag], capture_output=True, encoding="utf-8", errors="replace")
        assert result.returncode == 0, result.stderr
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        inventory[name] = {"version": result.stdout.splitlines()[:2], "sha256": digest, "bytes": target.stat().st_size}
    for dll in (ROOT / "tools" / "bin").glob("*.dll"):
        shutil.copy2(dll, native / dll.name)
    shutil.copytree(ROOT / "tools" / "licenses", destination / "tools" / "licenses", dirs_exist_ok=True)
    for name in ("LICENSE", "README.txt"):
        original = Path(found["ffmpeg"]).parent.parent / name
        if original.exists():
            target = destination / "tools" / "licenses" / "ffmpeg" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
    shutil.copy2(ROOT / "tools" / "mosaic-cli.toml", destination / "tools" / "mosaic-cli.toml")
    (destination / "BUNDLED_TOOLS.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print("BUNDLED TOOLS PASS")


if __name__ == "__main__":
    main()
