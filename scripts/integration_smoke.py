"""Exercise real Mosaic and oxipng. Add --live to upload only generated test imagery."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ptshot.core import ImageRecord, Job, Settings, atomic_text, png_dimensions
from ptshot.pipeline import Pipeline
from ptshot.tools import discover_tools


def make_png(width: int, height: int) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = (b"\0" + bytes((20, 90, 180)) * width) * height
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 0)) + chunk(b"IEND", b"")


def run_checked(command):
    result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    base = ROOT / "build" / "integration"
    base.mkdir(parents=True, exist_ok=True)
    paths = discover_tools(ROOT)
    assert len(paths) == 5, paths
    video = base / "合成 测试影片.mp4"
    run_checked([paths["ffmpeg"], "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                 "testsrc2=size=1280x720:rate=24", "-t", "6", "-c:v", "libx264", "-pix_fmt",
                 "yuv420p", "-y", str(video)])
    log = []
    pipeline = Pipeline(root=ROOT, log=log.append)
    job = pipeline.run([video], base / "capture", Settings(mode="both", count=2, cols=2, rows=2,
                                                             width=1280, upload=args.live))
    assert job.state == "completed", (job.state, job.errors, [r.error for r in job.records])
    assert len(job.records) == 3
    assert all((r.width, r.height) == (1280, 720) for r in job.records[:2])
    # Mosaic rounds each grid cell down to an even pixel width; keep its native output.
    assert 1280 - 2 * job.settings.cols < job.records[2].width <= 1280
    compressed_dir = base / "compression-job"
    original = compressed_dir / "originals" / "large.png"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(make_png(2048, 1720))
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    record = ImageRecord("generated-solid-color", str(original))
    compression_job = Job(compressed_dir, Settings(upload=args.live), [], [record])
    pipeline.process_records(compression_job)
    assert record.original_bytes > 10_000_000
    assert record.upload_bytes <= 10_000_000
    assert original_hash == hashlib.sha256(original.read_bytes()).hexdigest()
    def pixel_hash(path):
        return run_checked([paths["ffmpeg"], "-hide_banner", "-loglevel", "error", "-i", str(path),
                            "-pix_fmt", "rgb24", "-f", "hash", "-hash", "sha256", "-"])
    pixels = pixel_hash(original)
    assert pixels == pixel_hash(record.upload_path)
    assert png_dimensions(Path(record.upload_path)) == (2048, 1720)
    report = {"capture_session": str(job.directory / "session.json"), "images": 3,
              "original_dimensions": [1280, 720], "sheet_dimensions": [job.records[2].width, job.records[2].height],
              "compression_original_bytes": record.original_bytes,
              "compression_upload_bytes": record.upload_bytes, "source_sha256_unchanged": original_hash,
              "pixel_hash": pixels, "lossless": True, "live": args.live,
              "compression_session": str(compressed_dir / "session.json")}
    if args.live:
        import urllib.request
        for result_job in (job, compression_job):
            for item in result_job.records:
                assert item.status == "uploaded", item.error
                with urllib.request.urlopen(item.direct_url, timeout=90) as response:
                    remote = response.read()
                assert remote == Path(item.upload_path).read_bytes()
        report["remote_bytes_match"] = True
        report["uploaded"] = len(job.successful_urls) + len(compression_job.successful_urls)
    atomic_text(base / "REPORT.json", json.dumps(report, ensure_ascii=False, indent=2))
    atomic_text(base / "run.log", "\n".join(log))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("INTEGRATION PASS")


if __name__ == "__main__":
    main()
