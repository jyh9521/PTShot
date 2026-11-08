"""Archive and reopen the self-contained directory without any user output folders."""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    source = ROOT / "dist" / "PTShot-M3E"
    archive = ROOT / "dist" / "PTShot-0.2.0-Windows-x64.zip"
    assert source.resolve().is_relative_to((ROOT / "dist").resolve())
    assert archive.resolve().is_relative_to((ROOT / "dist").resolve())
    if shutil.disk_usage(archive.parent).free < sum(p.stat().st_size for p in source.rglob('*') if p.is_file()):
        raise RuntimeError("打包前的剩余空间检查未通过，请先腾出空间")
    temporary = archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for filename in sorted(source.rglob("*")):
            if filename.is_file() and not filename.is_relative_to(source / "output"):
                bundle.write(filename, filename.relative_to(source.parent))
    with zipfile.ZipFile(temporary) as bundle:
        assert bundle.testzip() is None
        assert "PTShot-M3E/PTShot.exe" in bundle.namelist()
        assert "PTShot-M3E/resources/worker/PTShotWorker.exe" in bundle.namelist()
        for tool in ("mosaic-cli", "oxipng", "ffmpeg", "ffprobe", "mediainfo"):
            assert f"PTShot-M3E/resources/tools/bin/{tool}.exe" in bundle.namelist()
        for name in ("desktop/main.cjs", "desktop/preload.cjs", "frontend-dist/index.html"):
            assert bundle.read(f"PTShot-M3E/resources/app/{name}") == (source / "resources/app" / name).read_bytes()
    temporary.replace(archive)
    with archive.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    (archive.parent / "PTShot-0.2.0-SHA256.txt").write_text(f"{sha256}  {archive.name}\n", encoding="ascii")
    print(f"ZIP={archive}\nBYTES={archive.stat().st_size}\nSHA256={sha256}\nARCHIVE PASS")


if __name__ == "__main__":
    main()
