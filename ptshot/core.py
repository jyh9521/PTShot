"""Pure contracts shared by the GUI, CLI and tests."""
from __future__ import annotations

import json
import os
import re
import struct
import tempfile
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

UPLOAD_LIMIT = 10_000_000  # Decimal MB: stay inside Pixhost's documented 10 MB limit.
PIXHOST_DOMAINS = ("pixhost.to", "pixhost.cc", "pixho.st")
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm", ".ts", ".m2ts",
                    ".mpg", ".mpeg", ".wmv", ".flv", ".vob", ".mts", ".mxf", ".ogv"}


class ShotError(Exception):
    """An actionable, user-facing operation failure."""


class Cancelled(ShotError):
    pass


def compression_required(size_bytes: int) -> bool:
    return size_bytes > UPLOAD_LIMIT


def pixhost_url(value: str, *, direct: bool = False) -> str:
    """Validate actual Pixhost URLs, not guessed thumbnail-host substitutions."""
    if not isinstance(value, str) or any(c.isspace() or c in "[]\\" for c in unquote(value)):
        raise ShotError("Pixhost 返回了格式异常的图片地址")
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as exc:
        raise ShotError("Pixhost 返回了格式异常的图片地址") from exc
    if (parts.scheme not in ("http", "https") or parts.username or parts.password or port
            or not any(host == d or host.endswith("." + d) for d in PIXHOST_DOMAINS)):
        raise ShotError("图片地址的域名不属于 Pixhost")
    if direct:
        if not re.fullmatch(r"img\d*\.(?:pixhost\.to|pixhost\.cc|pixho\.st)", host):
            raise ShotError("此地址不是 Pixhost 高清原图服务器")
        if not re.fullmatch(r"/images/[^/]+/[^/]+\.(?:png|jpe?g|gif|webp|avif)", parts.path, re.I):
            raise ShotError("此地址不是高清原图直链")
    elif not parts.path.startswith("/show/"):
        raise ShotError("Pixhost 返回的展示页地址异常")
    if parts.fragment or parts.query:
        raise ShotError("Pixhost 图片地址包含异常参数")
    return urlunsplit(("https", host, parts.path, "", ""))


def bbcode_for_urls(urls: list[str]) -> str:
    return "\n".join(f"[img]{pixhost_url(url, direct=True)}[/img]" for url in urls)


class _ImageParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.candidates: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        raw = None
        priority = 0
        if tag == "img":
            raw = values.get("src") or values.get("data-src")
            priority = 10 if values.get("id") == "image" else 1
        elif tag == "meta" and values.get("property") == "og:image":
            raw = values.get("content")
            priority = 2
        if raw:
            try:
                candidate = pixhost_url(urljoin(self.base, raw), direct=True)
            except ShotError:
                return
            self.candidates.append((priority, candidate))


def direct_url_from_html(page: str, show_url: str) -> str:
    parser = _ImageParser(pixhost_url(show_url))
    parser.feed(page)
    if not parser.candidates:
        raise ShotError("展示页未找到高清原图；展示页地址已保存，可稍后重试解析")
    highest = max(score for score, _ in parser.candidates)
    urls = {url for score, url in parser.candidates if score == highest}
    if len(urls) != 1:
        raise ShotError("展示页出现多个高清原图地址，请稍后重试解析")
    return urls.pop()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(33)
    if len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ShotError(f"不是有效的 PNG 图片：{path.name}")
    width, height = struct.unpack(">II", header[16:24])
    if not width or not height:
        raise ShotError(f"PNG 尺寸异常：{path.name}")
    return width, height


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class Settings:
    mode: str = "screenshots"
    count: int = 6
    cols: int = 4
    rows: int = 4
    width: int = 3840
    content_type: int = 0
    thumbnail_size: int = 350
    upload: bool = True
    optimization: int = 4
    tools: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if self.mode not in ("screenshots", "sheet", "both"):
            raise ShotError("请选择原尺寸截图、总览拼图或两者")
        for label, value, minimum, maximum in (
            ("截图张数", self.count, 1, 100), ("拼图列数", self.cols, 1, 12),
            ("拼图行数", self.rows, 1, 12), ("拼图宽度", self.width, 320, 16384),
            ("缩略图尺寸", self.thumbnail_size, 150, 500),
            ("优化等级", self.optimization, 0, 6), ("内容分类", self.content_type, 0, 1),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ShotError(f"{label}应为 {minimum}–{maximum} 之间的整数")
        if type(self.upload) is not bool or not isinstance(self.tools, dict):
            raise ShotError("设置格式异常")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in self.tools.items()):
            raise ShotError("依赖程序路径格式异常")

    @classmethod
    def from_dict(cls, value: dict) -> Settings:
        obj = cls(**{key: val for key, val in value.items() if key in cls.__dataclass_fields__})
        obj.validate()
        return obj


@dataclass
class ImageRecord:
    source_video: str
    original_path: str
    upload_path: str = ""
    original_bytes: int = 0
    upload_bytes: int = 0
    width: int = 0
    height: int = 0
    status: str = "pending"
    show_url: str = ""
    direct_url: str = ""
    thumbnail_url: str = ""
    error: str = ""


@dataclass
class Job:
    directory: Path
    settings: Settings
    videos: list[str]
    records: list[ImageRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    state: str = "running"

    @property
    def successful_urls(self) -> list[str]:
        return [r.direct_url for r in self.records if r.status == "uploaded" and r.direct_url]

    def save(self) -> None:
        payload = {"version": 1, "settings": asdict(self.settings), "videos": self.videos,
                   "records": [asdict(record) for record in self.records],
                   "errors": self.errors, "state": self.state}
        atomic_text(self.directory / "session.json", json.dumps(payload, ensure_ascii=False, indent=2))
        atomic_text(self.directory / "bbcode.txt", bbcode_for_urls(self.successful_urls))
        atomic_text(self.directory / "urls.txt", "\n".join(self.successful_urls))

    @classmethod
    def load(cls, path: Path) -> Job:
        path = path.resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ShotError("此任务记录的版本不受支持")
        job = cls(path.parent, Settings.from_dict(data["settings"]), data["videos"],
                  [ImageRecord(**item) for item in data["records"]],
                  data.get("errors", []), data.get("state", "interrupted"))
        for record in job.records:
            if record.status == "uploaded":
                record.direct_url = pixhost_url(record.direct_url, direct=True)
            if record.show_url:
                record.show_url = pixhost_url(record.show_url)
        return job
