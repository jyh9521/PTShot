"""Local tool discovery, pinned downloads and cancellable subprocesses."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .core import Cancelled, ShotError, atomic_text

TOOL_NAMES = ("mosaic-cli", "oxipng", "ffmpeg", "ffprobe", "mediainfo")
Log = Callable[[str], None]


def app_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", app_root()))


def discover_tools(root: Path, custom: dict[str, str] | None = None) -> dict[str, str]:
    found = {}
    for name in TOOL_NAMES:
        explicit = (custom or {}).get(name, "").strip().strip('"')
        if explicit:
            path = Path(explicit).expanduser()
            # A stale explicit selection is surfaced, never silently replaced.
            if path.is_file():
                found[name] = str(path.resolve())
            continue
        for directory in (root / "tools" / "bin", root / "tools", root):
            candidate = directory / (name + (".exe" if os.name == "nt" else ""))
            if candidate.is_file():
                found[name] = str(candidate.resolve())
                break
        else:
            candidate = shutil.which(name)
            if candidate:
                found[name] = candidate
    return found


def environment(paths: dict[str, str], root: Path) -> dict[str, str]:
    env = os.environ.copy()
    directories = list(dict.fromkeys(str(Path(p).parent) for p in paths.values()))
    env["PATH"] = os.pathsep.join(directories + [env.get("PATH", "")])
    config = root / "tools" / "mosaic-cli.toml"
    if not config.exists():
        config = resource_root() / "tools" / "mosaic-cli.toml"
    env["MOSAIC_CLI_CONFIG"] = str(config.resolve())
    return env


class Runner:
    def __init__(self, stop: threading.Event, log: Log, env: dict[str, str]):
        self.stop, self.log, self.env = stop, log, env

    def check(self) -> None:
        if self.stop.is_set():
            raise Cancelled("任务已取消，已完成的图片和上传结果已保留")

    def run(self, command: list[str], *, timeout: float = 3600) -> str:
        self.check()
        self.log("执行：" + subprocess.list2cmdline(command))
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=self.env, **options)
        started = time.monotonic()
        try:
            while True:
                try:
                    out, err = process.communicate(timeout=0.15)
                    break
                except subprocess.TimeoutExpired:
                    self.check()
                    if time.monotonic() - started > timeout:
                        raise ShotError(f"{Path(command[0]).name} 运行超时")
        except BaseException:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.communicate()
            raise
        stdout, stderr = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
        if stderr.strip():
            self.log(stderr.strip())
        self.check()
        if process.returncode:
            raise ShotError(f"{Path(command[0]).name} 退出码 {process.returncode}：{stderr[-2400:].strip()}")
        return stdout


def _download(url: str, target: Path, stop: threading.Event, log: Log,
              fallback_url: str | None = None) -> None:
    for attempt in range(3):
        try:
            actual_url = fallback_url if attempt and fallback_url else url
            request = urllib.request.Request(actual_url, headers={"User-Agent": "PTShot/0.1",
                                              "Accept": "application/octet-stream"})
            with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as stream:
                total = int(response.headers.get("Content-Length", 0))
                received, last = 0, -1
                while chunk := response.read(256 * 1024):
                    if stop.is_set():
                        raise Cancelled("依赖下载已取消")
                    stream.write(chunk)
                    received += len(chunk)
                    megabytes = received // 1_000_000
                    if megabytes // 10 != last:
                        last = megabytes // 10
                        log(f"下载 {megabytes} / {total // 1_000_000 or '?'} MB")
            return
        except Cancelled:
            raise
        except (OSError, ValueError) as exc:
            if attempt == 2:
                raise ShotError(f"依赖下载失败：{exc}") from exc
            log(f"下载中断，重试 {attempt + 1}/2")
            if stop.wait(attempt + 1):
                raise Cancelled("依赖下载已取消")


def install_missing(root: Path, custom: dict[str, str], log: Log,
                    stop: threading.Event | None = None) -> dict[str, str]:
    if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise ShotError("自动下载包适用于 Windows x64；请在设置中选择本机依赖程序")
    stop = stop or threading.Event()
    config = resource_root() / "dependencies.lock.json"
    lock = json.loads(config.read_text(encoding="utf-8"))
    destination = root / "tools" / "bin"
    destination.mkdir(parents=True, exist_ok=True)
    for package in lock["packages"]:
        current = discover_tools(root, custom)
        names = [Path(name).stem.lower() for name in package["files"].values()]
        if all(name in current for name in names):
            continue
        if any(custom.get(name, "").strip() and name not in current for name in names):
            raise ShotError("自定义依赖路径已失效；请修正路径或清空后再安装")
        log(f"安装 {package['id']} {package['version']}")
        with tempfile.TemporaryDirectory(prefix="ptshot-download-") as temporary:
            archive = Path(temporary) / "download"
            _download(package["url"], archive, stop, log, package.get("fallback_url"))
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != package["sha256"]:
                raise ShotError(f"{package['id']} SHA-256 校验不一致，请重试下载")
            log(f"SHA-256 校验通过：{digest}")
            if package["url"].endswith(".exe"):
                atomic_binary(destination / next(iter(package["files"].values())), archive.read_bytes())
            else:
                with zipfile.ZipFile(archive) as bundle:
                    for source, target in package["files"].items():
                        matches = [p for p in bundle.namelist() if Path(p).name.lower() == source.lower()]
                        if len(matches) != 1:
                            raise ShotError(f"{package['id']} 下载包内缺少 {source}")
                        atomic_binary(destination / target, bundle.read(matches[0]))
                    for member in bundle.namelist():
                        base = Path(member).name
                        if base.lower().endswith(".dll"):
                            atomic_binary(destination / base, bundle.read(member))
                        elif any(s in base.lower() for s in ("license", "licence", "copying")):
                            atomic_binary(root / "tools" / "licenses" / package["id"] / base,
                                          bundle.read(member))
    found = discover_tools(root, custom)
    missing = [name for name in TOOL_NAMES if name not in found]
    if missing:
        raise ShotError("依赖待配置：" + ", ".join(missing))
    log("全部 5 项依赖已就绪")
    return found


def atomic_binary(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".download-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
