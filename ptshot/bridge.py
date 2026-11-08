"""A single-operation JSON-lines worker for the Material 3 Expressive desktop shell."""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import __version__
from .core import Job, Settings, atomic_text
from .pipeline import Pipeline
from .tools import app_root, discover_tools, install_missing

OUTPUT_LOCK = threading.Lock()


def read_line() -> str:
    # Raw fd I/O avoids a daemon thread holding sys.stdin's buffered lock at shutdown.
    line = bytearray()
    while True:
        chunk = os.read(sys.stdin.fileno(), 1)
        if not chunk or chunk == b"\n":
            return line.decode("utf-8")
        line.extend(chunk)


def emit(kind: str, **data) -> None:
    with OUTPUT_LOCK:
        print(json.dumps({"type": kind, **data}, ensure_ascii=False), flush=True)


def job_snapshot(job: Job) -> dict:
    return {"directory": str(job.directory), "settings": asdict(job.settings), "videos": job.videos,
            "records": [asdict(record) for record in job.records], "errors": job.errors,
            "state": job.state, "successful_urls": job.successful_urls}


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    stop = threading.Event()
    try:
        request = json.loads(read_line())
        root = Path(os.environ.get("PTSHOT_ROOT", str(app_root()))).resolve()
        action = request["action"]
        settings = Settings.from_dict(request.get("settings", {}))
        def listen_for_cancel():
            while line := read_line():
                try:
                    if json.loads(line).get("action") == "cancel":
                        stop.set()
                except (ValueError, AttributeError):
                    pass
        threading.Thread(target=listen_for_cancel, daemon=True).start()
        logs = []
        def log(message):
            logs.append(datetime.now().strftime("%H:%M:%S  ") + message)
            emit("log", message=message)
        def changed(job):
            atomic_text(job.directory / "run.log", "\n".join(logs))
            emit("job", job=job_snapshot(job))
        pipeline = Pipeline(root=root, stop=stop, log=log, changed=changed)
        if action == "inspect":
            emit("result", tools=discover_tools(root, settings.tools), version=__version__)
        elif action == "install":
            paths = install_missing(root, settings.tools, lambda message: emit("log", message=message), stop)
            emit("result", tools=paths)
        elif action == "run":
            job = pipeline.run([Path(p) for p in request["videos"]], Path(request["output"]), settings)
            emit("result", job=job_snapshot(job))
        elif action in ("open", "resume"):
            job = Job.load(Path(request["session"]))
            if action == "resume":
                job.settings.tools = settings.tools
                job = pipeline.resume(job)
            else:
                job.save()
            emit("result", job=job_snapshot(job))
        else:
            raise ValueError("未知操作")
        emit("finished", ok=True)
    except Exception as exc:
        emit("error", message=str(exc))
        emit("finished", ok=False)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
