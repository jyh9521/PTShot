import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ptshot.core import Cancelled, ImageRecord, Job, Settings, ShotError
from ptshot.pipeline import Pipeline
from tests.helpers import png
from tests.test_core import SHOW, URL


class Client:
    def __init__(self, *, fail_resolve=False, stop_after_upload=None):
        self.uploads = self.resolves = 0
        self.fail_resolve = fail_resolve
        self.stop_after_upload = stop_after_upload

    def upload(self, *args):
        self.uploads += 1
        if self.stop_after_upload:
            self.stop_after_upload.set()
        return {"show_url": SHOW, "th_url": "thumbnail"}

    def resolve(self, *args):
        self.resolves += 1
        if self.fail_resolve:
            raise ShotError("temporary GET failure")
        return URL


class NoopRunner:
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append(command)
        return ""


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / "job"
        self.original = self.directory / "originals" / "video" / "screenshot.png"
        self.original.parent.mkdir(parents=True)
        self.original.write_bytes(png())
        self.record = ImageRecord("video.mp4", str(self.original))
        self.job = Job(self.directory, Settings(), ["video.mp4"], [self.record])

    def pipeline(self, client=None, **kwargs):
        return Pipeline(root=self.root, client=client or Client(), log=lambda _: None, **kwargs)

    def test_small_png_skips_optimizer(self):
        runner = NoopRunner()
        path = self.pipeline(runner=runner).prepare(self.record, self.job)
        self.assertEqual(path, self.original)
        self.assertEqual(runner.calls, [])

    def test_exact_threshold_skips_optimizer(self):
        with self.original.open("ab") as stream:
            stream.truncate(10_000_000)
        runner = NoopRunner()
        self.pipeline(runner=runner).prepare(self.record, self.job)
        self.assertEqual(runner.calls, [])

    def test_oversize_optimized_copy_original_retained_no_upload(self):
        self.original.write_bytes(png(2048, 1720, level=0))
        before = self.original.read_bytes()
        client = Client()
        runner = NoopRunner()
        with patch("ptshot.pipeline.discover_tools", return_value={"oxipng": "oxipng.exe"}):
            self.pipeline(client, runner=runner).process_records(self.job)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(self.original.read_bytes(), before)
        self.assertNotEqual(runner.calls[0][-1], str(self.original))
        self.assertEqual(self.record.status, "oversize")
        self.assertEqual(client.uploads, 0)
        self.assertEqual(self.job.state, "partial")

    def test_optimized_copy_under_limit_used(self):
        self.original.write_bytes(png(2048, 1720, level=0))
        before = self.original.read_bytes()
        class Compressor:
            def run(self, command, **kwargs):
                Path(command[-1]).write_bytes(png(2048, 1720))
        with patch("ptshot.pipeline.discover_tools", return_value={"oxipng": "oxipng.exe"}):
            selected = self.pipeline(runner=Compressor()).prepare(self.record, self.job)
        self.assertNotEqual(selected, self.original)
        self.assertLess(self.record.upload_bytes, 10_000_000)
        self.assertEqual(self.original.read_bytes(), before)

    def test_missing_optimizer_actionable(self):
        self.original.write_bytes(png(2048, 1720, level=0))
        with patch("ptshot.pipeline.discover_tools", return_value={}):
            self.pipeline().process_records(self.job)
        self.assertEqual(self.record.status, "error")
        self.assertIn("oxipng", self.record.error)

    def test_success_is_exported(self):
        client = Client()
        self.pipeline(client).process_records(self.job)
        self.assertEqual(client.uploads, 1)
        self.assertEqual(self.record.status, "uploaded")
        self.assertEqual((self.directory / "bbcode.txt").read_text(), f"[img]{URL}[/img]")

    def test_resolve_failure_then_resume_does_not_reupload(self):
        client = Client(fail_resolve=True)
        pipeline = self.pipeline(client)
        pipeline.process_records(self.job)
        self.assertEqual(self.record.status, "error")
        restored = Job.load(self.directory / "session.json")
        self.assertEqual(restored.records[0].show_url, SHOW)
        client.fail_resolve = False
        pipeline.resume(restored)
        self.assertEqual(client.uploads, 1)
        self.assertEqual(client.resolves, 2)
        self.assertEqual(restored.records[0].status, "uploaded")

    def test_successful_uploads_skipped_on_resume(self):
        client = Client()
        pipeline = self.pipeline(client)
        pipeline.process_records(self.job)
        pipeline.resume(Job.load(self.directory / "session.json"))
        self.assertEqual((client.uploads, client.resolves), (1, 1))

    def test_local_only_then_explicit_upload(self):
        client = Client()
        self.job.settings.upload = False
        pipeline = self.pipeline(client)
        pipeline.process_records(self.job)
        self.assertEqual(self.record.status, "local")
        self.assertEqual(client.uploads, 0)
        pipeline.resume(self.job)
        self.assertEqual(client.uploads, 1)
        self.assertEqual(self.record.status, "uploaded")

    def test_cancel_after_post_receipt_is_persisted(self):
        stop = threading.Event()
        client = Client(stop_after_upload=stop)
        pipeline = self.pipeline(client, stop=stop)
        with self.assertRaises(Cancelled):
            pipeline.process_records(self.job)
        restored = Job.load(self.directory / "session.json")
        self.assertEqual(restored.records[0].show_url, SHOW)
        self.assertEqual(restored.records[0].status, "resolving")
        stop.clear()
        pipeline.resume(restored)
        self.assertEqual(client.uploads, 1)

    def test_per_image_failure_does_not_drop_others(self):
        bad = ImageRecord("v", str(self.directory / "missing.png"))
        self.job.records.insert(0, bad)
        self.pipeline().process_records(self.job)
        self.assertEqual(bad.status, "error")
        self.assertEqual(self.record.status, "uploaded")
        self.assertEqual(self.job.state, "partial")

    def test_empty_inputs_not_accepted(self):
        with self.assertRaises(ShotError):
            self.pipeline().run([], self.root, Settings())

    def test_missing_inputs_not_accepted(self):
        with self.assertRaises(ShotError):
            self.pipeline().run([self.root / "missing.mp4"], self.root, Settings())
