import io
import struct
import zlib
from email.message import Message


def png(width=16, height=12, *, level=6):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\0" + bytes([31, 97, 211]) * width
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(row * height, level)) + chunk(b"IEND", b"")


class Response(io.BytesIO):
    def __init__(self, data, url, mime="application/json"):
        super().__init__(data)
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = mime
        self.status = 200

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, **kwargs):
        self.calls.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
