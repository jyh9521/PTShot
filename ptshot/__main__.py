"""GUI by default; scriptable local batch operation when a subcommand is supplied."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import Job, Settings, ShotError
from .pipeline import Pipeline
from .tools import TOOL_NAMES, app_root, discover_tools, install_missing


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) == 1 or sys.argv[1] == "gui":
        from .gui import launch
        launch()
        return
    parser = argparse.ArgumentParser(description="PT Shot · Mosaic + oxipng + Pixhost")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="显示依赖路径")
    sub.add_parser("install-tools", help="下载并校验缺少的 Windows x64 依赖")
    run = sub.add_parser("run", help="截图、优化并上传")
    run.add_argument("videos", nargs="+", type=Path)
    run.add_argument("--output", type=Path, default=app_root() / "output")
    run.add_argument("--count", type=int, default=6)
    run.add_argument("--mode", choices=("screenshots", "sheet", "both"), default="screenshots")
    run.add_argument("--cols", type=int, default=4)
    run.add_argument("--rows", type=int, default=4)
    run.add_argument("--width", type=int, default=3840)
    run.add_argument("--content-type", type=int, choices=(0, 1), default=0)
    run.add_argument("--no-upload", action="store_true")
    resume = sub.add_parser("resume", help="继续已有任务的未完成图片；跳过已成功上传的图片")
    resume.add_argument("session", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            paths = discover_tools(app_root())
            print(json.dumps({name: paths.get(name, "MISSING") for name in TOOL_NAMES}, ensure_ascii=False, indent=2))
            raise SystemExit(0 if len(paths) == len(TOOL_NAMES) else 1)
        if args.command == "install-tools":
            install_missing(app_root(), {}, print)
            return
        pipeline = Pipeline()
        if args.command == "run":
            settings = Settings(mode=args.mode, count=args.count, cols=args.cols, rows=args.rows,
                                width=args.width, content_type=args.content_type, upload=not args.no_upload)
            job = pipeline.run(args.videos, args.output, settings)
        else:
            job = pipeline.resume(Job.load(args.session))
        print(f"SESSION={job.directory / 'session.json'}")
        print(f"RESULT state={job.state} images={len(job.records)} uploaded={len(job.successful_urls)}")
        raise SystemExit(0 if job.state == "completed" else 1)
    except (ShotError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
