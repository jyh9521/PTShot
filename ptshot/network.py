"""Pixhost v2: multipart upload, original-image resolution and verification."""
from __future__ import annotations

import json
import struct
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .core import (UPLOAD_LIMIT, Cancelled, ShotError, direct_url_from_html,
                   pixhost_url, png_dimensions)


def multipart_image(path: Path, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "PTShot" + uuid.uuid4().hex
    blocks = []
    for key, value in fields.items():
        blocks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    # ASCII transport name avoids header injection and inconsistent Unicode handling.
    blocks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="img"; '
                   'filename="ptshot.png"\r\nContent-Type: image/png\r\n\r\n').encode())
    blocks.extend((path.read_bytes(), f"\r\n--{boundary}--\r\n".encode()))
    return b"".join(blocks), f"multipart/form-data; boundary={boundary}"


class PixhostClient:
    def __init__(self, stop: threading.Event | None = None, *, timeout: int = 90,
                 opener=None):
        self.stop = stop or threading.Event()
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener()

    def check(self) -> None:
        if self.stop.is_set():
            raise Cancelled("任务已取消，已完成的上传结果已保留")

    def request(self, request: urllib.request.Request, *, limit: int = 2_000_000,
                retry: bool = False) -> tuple[bytes, object, str]:
        attempts = 3 if retry else 1
        for attempt in range(attempts):
            self.check()
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    data = response.read(limit + 1)
                    if len(data) > limit:
                        raise ShotError("Pixhost 返回内容超过预期大小")
                    # Do not discard an upload receipt if Cancel was clicked during the POST.
                    return data, response.headers, response.geturl()
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                status = getattr(exc, "code", 0)
                if attempt + 1 < attempts and (not status or status in (404, 408, 429, 500, 502, 503, 504)):
                    if self.stop.wait(1 + attempt * 2):
                        self.check()
                    continue
                raise ShotError(f"Pixhost 网络请求失败：{exc}") from exc
        raise AssertionError("unreachable")

    def upload(self, path: Path, content_type: int, thumbnail_size: int) -> dict[str, str]:
        self.check()
        if path.stat().st_size > UPLOAD_LIMIT:
            raise ShotError("图片超过 10MB，已停止本张上传")
        png_dimensions(path)
        body, content_header = multipart_image(path, {
            "content_type": str(content_type), "max_th_size": str(thumbnail_size),
            "optimize_for_web": "0",  # Retain original resolution, PNG format and pixels.
        })
        request = urllib.request.Request("https://api.pixhost.to/images", data=body,
            headers={"Accept": "application/json", "Content-Type": content_header,
                     "User-Agent": "PTShot/0.1"}, method="POST")
        # Never automatically replay POST: a lost response may still mean a completed upload.
        data, _, _ = self.request(request)
        try:
            receipt = json.loads(data)
            show = pixhost_url(receipt["show_url"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ShotError("Pixhost 上传未返回有效的展示页地址") from exc
        return {"show_url": show, "th_url": str(receipt.get("th_url", ""))}

    def resolve(self, show_url: str, expected_dimensions: tuple[int, int]) -> str:
        show_url = pixhost_url(show_url)
        request = urllib.request.Request(show_url, headers={"User-Agent": "PTShot/0.1",
                                                           "Accept": "text/html"})
        data, _, final = self.request(request, retry=True)
        pixhost_url(final)
        url = direct_url_from_html(data.decode("utf-8", "replace"), show_url)
        self.verify(url, expected_dimensions)
        self.check()
        return url

    def verify(self, url: str, expected_dimensions: tuple[int, int]) -> None:
        url = pixhost_url(url, direct=True)
        request = urllib.request.Request(url, headers={"Range": "bytes=0-32",
            "User-Agent": "PTShot/0.1", "Referer": "https://pixhost.to/"})
        # Read only the PNG header even if the image server ignores Range.
        self.check()
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    pixhost_url(response.geturl(), direct=True)
                    data = response.read(33)
                    mime = response.headers.get_content_type()
                if mime != "image/png" or len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
                    raise ShotError("高清直链未返回 PNG 原图")
                actual = struct.unpack(">II", data[16:24])
                if actual != expected_dimensions:
                    raise ShotError(f"原图尺寸校验失败：期望 {expected_dimensions}，实际 {actual}")
                return
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == 2:
                    raise ShotError(f"高清原图连通性校验失败：{exc}") from exc
                if self.stop.wait(attempt + 1):
                    self.check()
