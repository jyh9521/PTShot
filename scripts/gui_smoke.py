"""Own-app widget integration test: capture, result rendering and actual clipboard copy."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["APPDATA"] = str(ROOT / "build" / "gui-smoke" / "appdata")

import tkinter as tk
from ptshot.core import Job, atomic_text, bbcode_for_urls
from ptshot.gui import Application


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = tk.Tk()
    app = Application(root)
    app.upload.set(False)
    app.count.set("2")
    app.output.set(str(ROOT / "build" / "gui-smoke" / "output"))
    app.add_paths([ROOT / "build" / "test-media" / "测试影片 sample.mp4"])
    root.update()
    app.start_button.invoke()
    deadline = time.monotonic() + 60
    while app.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.03)
    assert not app.busy, "GUI worker timed out"
    assert app.job and app.job.state == "completed"
    assert len(app.job.records) == 2
    assert len(app.result_tree.get_children()) == 2
    app.result_tree.selection_set("0")
    app._selection()
    root.update()
    assert app.preview_image is not None
    # Reopen a real upload receipt; copy all exact [img] direct-link [/img] lines.
    live = max((ROOT / "build" / "live-smoke").glob("PTShot-*/session.json"), key=lambda p: p.stat().st_mtime)
    app.job = Job.load(live)
    app._render_results()
    app.copy_all(True)
    root.update()
    expected = bbcode_for_urls(app.job.successful_urls)
    assert root.clipboard_get() == expected
    assert app.bbcode.get("1.0", "end-1c") == expected
    report = {"gui_capture": "PASS", "gui_records": 2, "preview": "PASS",
              "clipboard_exact_bbcode": expected, "clipboard_test": "PASS",
              "worker_thread_completed": True}
    atomic_text(ROOT / "build" / "gui-smoke" / "REPORT.json", json.dumps(report, ensure_ascii=False, indent=2))
    app.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("GUI PASS")


if __name__ == "__main__":
    main()
