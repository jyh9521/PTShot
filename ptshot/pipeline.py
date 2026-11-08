"""Mosaic capture → conditional lossless optimization → Pixhost → durable exports."""
from __future__ import annotations

import hashlib
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from .core import (Cancelled, ImageRecord, Job, Settings, ShotError,
                   compression_required, png_dimensions)
from .network import PixhostClient
from .tools import Runner, app_root, discover_tools, environment


class Pipeline:
    def __init__(self, *, root: Path | None = None, stop: threading.Event | None = None,
                 log: Callable[[str], None] = print, changed: Callable[[Job], None] = lambda _: None,
                 client: PixhostClient | None = None, runner: Runner | None = None):
        self.root = root or app_root()
        self.stop = stop or threading.Event()
        self.log, self.changed = log, changed
        self.client = client or PixhostClient(self.stop)
        self.runner = runner

    def check(self) -> None:
        if self.stop.is_set():
            raise Cancelled("任务已取消，已完成的图片和上传结果已保留")

    def checkpoint(self, job: Job) -> None:
        job.save()
        self.changed(job)

    def _runner(self, job: Job, *, capture: bool) -> Runner:
        if self.runner is not None:
            return self.runner
        paths = discover_tools(self.root, job.settings.tools)
        needed = ["mosaic-cli", "ffmpeg", "ffprobe", "mediainfo"] if capture else []
        missing = [name for name in needed if name not in paths]
        if missing:
            raise ShotError("请先安装或配置依赖：" + ", ".join(missing))
        return Runner(self.stop, self.log, environment(paths, self.root))

    def run(self, videos: list[Path], output: Path, settings: Settings) -> Job:
        settings.validate()
        videos = list(dict.fromkeys(path.expanduser().resolve() for path in videos))
        if not videos:
            raise ShotError("请先添加影片")
        for video in videos:
            if not video.is_file():
                raise ShotError(f"影片不存在：{video}")
        directory = output.expanduser().resolve() / datetime.now().strftime("PTShot-%Y%m%d-%H%M%S-%f")
        directory.mkdir(parents=True, exist_ok=False)
        job = Job(directory, settings, [str(path) for path in videos])
        self.checkpoint(job)
        try:
            runner = self._runner(job, capture=True)
            paths = discover_tools(self.root, settings.tools)
            for index, video in enumerate(videos, 1):
                self.check()
                stem = re.sub(r"[^\w.-]", "_", video.stem)[:100].strip(".") or "video"
                fingerprint = hashlib.sha256(str(video).encode()).hexdigest()[:8]
                capture_dir = directory / "originals" / f"{index:03d}_{stem}_{fingerprint}"
                capture_dir.mkdir(parents=True)
                modes = ["screenshots", "sheet"] if settings.mode == "both" else [settings.mode]
                for mode in modes:
                    self.check()
                    self.log(f"[{index}/{len(videos)}] {video.name} · {mode}")
                    mode_dir = capture_dir / mode
                    mode_dir.mkdir()
                    command = [paths["mosaic-cli"], mode, "--format", "png", "--quiet",
                               "--output", str(mode_dir)]
                    if mode == "screenshots":
                        command += ["--count", str(settings.count), "--suffix", "_screens_"]
                    else:
                        command += ["--cols", str(settings.cols), "--rows", str(settings.rows),
                                    "--width", str(settings.width), "--gap", "10", "--theme", "dark",
                                    "--timestamps", "--header", "--no-header-title", "--suffix", "_sheet"]
                    command += ["--", str(video)]
                    try:
                        runner.run(command)
                        generated = sorted(mode_dir.glob("*.png"))
                        expected = settings.count if mode == "screenshots" else 1
                        if len(generated) != expected:
                            raise ShotError(f"预期 {expected} 张，实际生成 {len(generated)} 张")
                        for image in generated:
                            width, height = png_dimensions(image)
                            record = ImageRecord(str(video), str(image), original_bytes=image.stat().st_size,
                                                 width=width, height=height)
                            job.records.append(record)
                        self.checkpoint(job)
                    except Cancelled:
                        raise
                    except (ShotError, OSError) as exc:
                        error = f"{video.name} / {mode}：{exc}"
                        job.errors.append(error)
                        self.log(error)
                        self.checkpoint(job)
            self.process_records(job)
        except Cancelled as exc:
            job.state = "cancelled"
            self.log(str(exc))
        except (ShotError, OSError) as exc:
            job.state = "failed"
            job.errors.append(str(exc))
            self.log(str(exc))
        finally:
            self.checkpoint(job)
        return job

    def prepare(self, record: ImageRecord, job: Job) -> Path:
        original = Path(record.original_path)
        width, height = png_dimensions(original)
        record.width, record.height = width, height
        record.original_bytes = original.stat().st_size
        selected = original
        if compression_required(record.original_bytes):
            paths = discover_tools(self.root, job.settings.tools)
            if "oxipng" not in paths:
                raise ShotError("图片超过 10MB，请在依赖设置中安装 oxipng 后重试")
            relative = original.relative_to(job.directory / "originals")
            optimized = job.directory / "optimized" / relative
            optimized.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, optimized)
            self.log(f"{original.name}：{record.original_bytes / 1_000_000:.2f} MB，调用 oxipng 无损优化")
            self._runner(job, capture=False).run([
                paths["oxipng"], "-o", str(job.settings.optimization), "--strip", "safe",
                "--timeout", "120", "--", str(optimized)], timeout=600)
            if png_dimensions(optimized) != (width, height):
                raise ShotError("优化后图片尺寸变化，已停止本张上传")
            if optimized.stat().st_size < record.original_bytes:
                selected = optimized
        record.upload_path = str(selected)
        record.upload_bytes = selected.stat().st_size
        if compression_required(record.upload_bytes):
            record.status = "oversize"
            raise ShotError(f"无损优化后仍为 {record.upload_bytes / 1_000_000:.2f} MB（超过 10MB）；原图已保留")
        return selected

    def process_records(self, job: Job) -> None:
        for index, record in enumerate(job.records, 1):
            self.check()
            if record.status == "uploaded":
                continue
            self.log(f"处理图片 [{index}/{len(job.records)}] {Path(record.original_path).name}")
            record.error = ""
            try:
                # Receipt is checkpointed before GET resolution, so retry won't upload it twice.
                if not record.show_url:
                    selected = self.prepare(record, job)
                    if not job.settings.upload:
                        record.status = "local"
                        self.checkpoint(job)
                        continue
                    self.check()
                    record.status = "uploading"
                    self.checkpoint(job)
                    receipt = self.client.upload(selected, job.settings.content_type,
                                                 job.settings.thumbnail_size)
                    record.show_url = receipt["show_url"]
                    record.thumbnail_url = receipt.get("th_url", "")
                    record.status = "resolving"
                    self.checkpoint(job)
                self.check()
                record.direct_url = self.client.resolve(record.show_url, (record.width, record.height))
                record.status = "uploaded"
                self.log("高清直链：" + record.direct_url)
            except Cancelled:
                raise
            except (ShotError, OSError, ValueError) as exc:
                if record.status != "oversize":
                    record.status = "error"
                record.error = str(exc)
                self.log(f"{Path(record.original_path).name}：{exc}")
            self.checkpoint(job)
        failed = any(record.status in ("error", "oversize") for record in job.records)
        job.state = "partial" if failed or job.errors else "completed"
        self.checkpoint(job)

    def resume(self, job: Job, *, upload: bool = True) -> Job:
        job.settings.upload = upload
        job.settings.validate()
        job.state = "running"
        try:
            self.process_records(job)
        except Cancelled as exc:
            job.state = "cancelled"
            self.log(str(exc))
        finally:
            self.checkpoint(job)
        return job
