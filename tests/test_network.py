import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from ptshot.core import ShotError
from ptshot.network import PixhostClient, multipart_image
from tests.helpers import Opener, Response, png
from tests.test_core import SHOW, URL


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.image = Path(self.temporary.name) / '中文 截图.png'
        self.image.write_bytes(png())

    def test_multipart_keeps_pixels_and_has_boundary(self):
        body, content_type = multipart_image(self.image, {"content_type": "0"})
        boundary = content_type.split("boundary=")[1]
        self.assertTrue(body.endswith(f"--{boundary}--\r\n".encode()))
        self.assertIn(self.image.read_bytes(), body)
        self.assertNotIn('中文'.encode(), body)
        self.assertIn(b'filename="ptshot.png"', body)

    def test_upload_contract_disables_lossy_server_optimization(self):
        opener = Opener(Response(json.dumps({"show_url": SHOW, "th_url": "thumbnail"}).encode(), "https://api.pixhost.to/images"))
        receipt = PixhostClient(opener=opener).upload(self.image, 1, 400)
        self.assertEqual(receipt["show_url"], SHOW)
        request = opener.calls[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.full_url, "https://api.pixhost.to/images")
        self.assertIn(b'name="optimize_for_web"\r\n\r\n0', request.data)
        self.assertIn(b'name="content_type"\r\n\r\n1', request.data)
        self.assertIn(b'name="max_th_size"\r\n\r\n400', request.data)

    def test_upload_is_not_automatically_replayed(self):
        opener = Opener(urllib.error.URLError("response lost"))
        with self.assertRaises(ShotError):
            PixhostClient(opener=opener).upload(self.image, 0, 350)
        self.assertEqual(len(opener.calls), 1)

    def test_invalid_upload_responses(self):
        for response in (b"bad json", b"{}", b"[]"):
            with self.subTest(response=response), self.assertRaises(ShotError):
                PixhostClient(opener=Opener(Response(response, "https://api.pixhost.to/images"))).upload(self.image, 0, 350)

    def test_oversize_not_sent(self):
        with self.image.open("ab") as stream:
            stream.truncate(10_000_001)
        opener = Opener()
        with self.assertRaises(ShotError):
            PixhostClient(opener=opener).upload(self.image, 0, 350)
        self.assertEqual(opener.calls, [])

    def test_original_resolution_verified(self):
        opener = Opener(Response(f'<img id="image" src="{URL}">'.encode(), SHOW, "text/html"),
                        Response(png(), URL, "image/png"))
        self.assertEqual(PixhostClient(opener=opener).resolve(SHOW, (16, 12)), URL)
        self.assertEqual(opener.calls[1].get_header("Range"), "bytes=0-32")

    def test_smaller_image_or_html_is_rejected(self):
        for data, mime, dimensions in ((png(8, 6), "image/png", (16, 12)),
                                        (b"<html>no image</html>", "text/html", (16, 12)),
                                        (b"\x89PNG\r\n\x1a\n", "image/png", (16, 12))):
            with self.subTest(mime=mime), self.assertRaises(ShotError):
                PixhostClient(opener=Opener(Response(data, URL, mime))).verify(URL, dimensions)

    def test_cancelled_upload_not_started(self):
        client = PixhostClient(opener=Opener())
        client.stop.set()
        with self.assertRaises(ShotError):
            client.upload(self.image, 0, 350)
