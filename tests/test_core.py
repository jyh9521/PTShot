import json
import tempfile
import unittest
from pathlib import Path

from ptshot.core import (UPLOAD_LIMIT, ImageRecord, Job, Settings, ShotError, atomic_text,
                         bbcode_for_urls, compression_required, direct_url_from_html,
                         pixhost_url, png_dimensions)
from tests.helpers import png

URL = "https://img3.pixhost.to/images/7020/123_example.png"
SHOW = "https://pixhost.to/show/7020/123_example.png"


class CoreTests(unittest.TestCase):
    def test_threshold_boundaries(self):
        for size in (0, UPLOAD_LIMIT - 1, UPLOAD_LIMIT):
            self.assertFalse(compression_required(size))
        self.assertTrue(compression_required(UPLOAD_LIMIT + 1))

    def test_exact_bbcode_and_order(self):
        other = URL.replace("123_", "124_")
        self.assertEqual(bbcode_for_urls([URL, other]), f"[img]{URL}[/img]\n[img]{other}[/img]")
        self.assertEqual(bbcode_for_urls([]), "")

    def test_bbcode_rejects_thumbnail_show_and_injection(self):
        for url in (SHOW, URL.replace("img3.", "t3."), URL.replace("/images/", "/thumbs/"),
                    URL + "[/img]", URL + "%5Bimg%5D", URL.replace(".to/", ".to.evil.test/")):
            with self.subTest(url=url), self.assertRaises(ShotError):
                bbcode_for_urls([url])

    def test_url_scheme_upgraded(self):
        self.assertEqual(pixhost_url(URL.replace("https:", "http:"), direct=True), URL)

    def test_foreign_or_malformed_urls(self):
        for value in ("file:///etc/passwd", "https://user@pixhost.to/show/1/a.png", "https://pixhost.to:443/show/1/a.png",
                      SHOW + "?x=y", SHOW + "#x", SHOW + "\r\n", "https://pixhost.to:bad/show/1/a.png", "javascript:alert(1)"):
            with self.subTest(value=value), self.assertRaises(ShotError):
                pixhost_url(value)

    def test_three_supported_domains(self):
        for domain in ("pixhost.to", "pixhost.cc", "pixho.st"):
            self.assertEqual(pixhost_url(URL.replace("pixhost.to", domain), direct=True), URL.replace("pixhost.to", domain))

    def test_parser_uses_actual_image_not_thumbnail_guess(self):
        html = f'<img src="https://t99.pixhost.to/thumbs/7020/123_example.png"><img id="image" src="{URL}">'
        self.assertEqual(direct_url_from_html(html, SHOW), URL)

    def test_parser_priority(self):
        other = URL.replace("123_", "999_")
        html = f'<meta property="og:image" content="{other}"><img id="image" src="{URL}">'
        self.assertEqual(direct_url_from_html(html, SHOW), URL)

    def test_protocol_relative_image(self):
        html = '<img id="image" src="' + URL.replace("https:", "") + '">'
        self.assertEqual(direct_url_from_html(html, SHOW), URL)

    def test_duplicate_candidates_not_ambiguous(self):
        self.assertEqual(direct_url_from_html(f'<img src="{URL}"><img src="{URL}">', SHOW), URL)

    def test_parser_missing_or_ambiguous(self):
        for html in ("<html>challenge</html>", f'<img src="{URL}"><img src="{URL.replace("123_", "456_")}">'):
            with self.assertRaises(ShotError):
                direct_url_from_html(html, SHOW)

    def test_defaults_and_settings_roundtrip(self):
        Settings().validate()
        self.assertEqual(Settings.from_dict({"count": 4, "future_field": 99}).count, 4)

    def test_settings_validation(self):
        for key, value in (("count", 0), ("count", True), ("count", "6"), ("mode", "reel"),
                           ("width", 20), ("rows", 13), ("content_type", 2), ("optimization", 7),
                           ("thumbnail_size", 501), ("upload", 1), ("tools", {"ffmpeg": 3})):
            with self.subTest(key=key, value=value), self.assertRaises(ShotError):
                Settings.from_dict({key: value})

    def test_png_header_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "中文.png"
            image.write_bytes(png(20, 10))
            self.assertEqual(png_dimensions(image), (20, 10))
            image.write_bytes(b"not png")
            with self.assertRaises(ShotError):
                png_dimensions(image)

    def test_manifest_only_exports_successful_original_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            success = ImageRecord("v", "a.png", status="uploaded", direct_url=URL, show_url=SHOW)
            failed = ImageRecord("v", "b.png", status="error", direct_url=URL.replace("123_", "124_"))
            job = Job(directory, Settings(), ["v"], [success, failed])
            job.save()
            self.assertEqual((directory / "bbcode.txt").read_text(), f"[img]{URL}[/img]")
            self.assertEqual((directory / "urls.txt").read_text(), URL)
            restored = Job.load(directory / "session.json")
            self.assertEqual(restored.successful_urls, [URL])
            self.assertEqual(restored.records[1].status, "error")

    def test_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "x.txt"
            atomic_text(path, "中文\n")
            atomic_text(path, "new")
            self.assertEqual(path.read_text(), "new")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_manifest_version_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            path.write_text(json.dumps({"version": 99}))
            with self.assertRaises(ShotError):
                Job.load(path)
