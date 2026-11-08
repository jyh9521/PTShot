"""Chinese Windows desktop front-end; all file/network work stays off Tk's thread."""
from __future__ import annotations

import json
import math
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .core import (VIDEO_EXTENSIONS, Job, Settings, ShotError, atomic_text,
                   bbcode_for_urls, pixhost_url)
from .pipeline import Pipeline
from .tools import TOOL_NAMES, app_root, discover_tools, install_missing

BG, CARD, INK, MUTED, BLUE = "#f3f6fb", "#ffffff", "#14243b", "#62728a", "#2463eb"
STATES = {"pending": "待处理", "local": "本地已就绪", "uploading": "上传中", "resolving": "解析原图中",
          "uploaded": "已上传 · 高清", "error": "失败 · 可重试", "oversize": "优化后仍超 10MB"}
MODES = {"原尺寸截图": "screenshots", "总览拼图": "sheet", "截图 + 拼图": "both"}
JOB_STATES = {"running": "处理中", "completed": "已完成", "partial": "部分完成", "failed": "处理失败",
              "cancelled": "已取消", "interrupted": "已中断"}


def config_path() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / ".config")) / "PTShot" / "settings.json"


class Application:
    def __init__(self, root: tk.Tk):
        self.root, self.base = root, app_root()
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.closing = False
        self.videos: list[Path] = []
        self.job: Job | None = None
        self.preview_image = None
        self.defaults = Settings()
        self.config_error = ""
        self.output_default = str(self.base / "output")
        try:
            saved = json.loads(config_path().read_text(encoding="utf-8"))
            self.defaults = Settings.from_dict(saved.get("settings", {}))
            self.output_default = saved.get("output", self.output_default)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, ShotError) as exc:
            self.config_error = f"设置已重置：{exc}"
        self.custom = dict(self.defaults.tools)
        self.root.title(f"PT Shot · 影片截图与图床上传  {__version__}")
        self.root.geometry("1160x860")
        self.root.minsize(980, 760)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._style()
        self._build()
        self.refresh_tools()
        self._log(self.config_error or "就绪。添加影片后，点击「开始截图并上传」。")
        self.root.after(100, self._poll)

    def _style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), foreground=INK, background=BG)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG)
        style.configure("Card.TLabel", background=CARD)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 24, "bold"))
        style.configure("TLabelframe", background=BG, bordercolor="#dbe3ee")
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TButton", padding=(12, 7), borderwidth=0, background="#e7edf7")
        style.map("TButton", background=[("active", "#d6e3fb")], foreground=[("disabled", "#9aa6b8")])
        style.configure("Primary.TButton", foreground="white", background=BLUE, font=("Microsoft YaHei UI", 11, "bold"))
        style.map("Primary.TButton", background=[("disabled", "#a9bce7"), ("active", "#174fc9")],
                  foreground=[("disabled", "#f0f3f9")])
        style.configure("TNotebook", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(20, 10))
        style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", BLUE)])
        style.configure("Treeview", background=CARD, fieldbackground=CARD, rowheight=32, borderwidth=0)
        style.configure("Treeview.Heading", background="#eaf0f8", padding=8)
        style.map("Treeview", background=[("selected", "#dce8ff")], foreground=[("selected", INK)])
        style.configure("TEntry", fieldbackground=CARD, padding=5)
        style.configure("TCombobox", fieldbackground=CARD, padding=5)

    def _build(self):
        main = ttk.Frame(self.root, padding=24)
        main.pack(fill="both", expand=True)
        title = ttk.Frame(main)
        title.pack(fill="x")
        ttk.Label(title, text="PT Shot", style="Title.TLabel").pack(side="left")
        ttk.Label(title, text="原尺寸截图 · 无损优化 · 高清直链", style="Muted.TLabel").pack(side="left", padx=20, pady=(14, 0))
        ttk.Label(title, text=f"v{__version__}", style="Muted.TLabel").pack(side="right", pady=(14, 0))
        flow = ttk.Frame(main, padding=(0, 14, 0, 18))
        flow.pack(fill="x")
        ttk.Label(flow, text="01  Mosaic 截图     →     02  > 10MB 时 oxipng 优化     →     03  Pixhost 上传     →     04  复制 BBCode",
                  foreground=BLUE).pack(anchor="w")
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill="both", expand=True)
        self.work = ttk.Frame(self.tabs, padding=16)
        self.results = ttk.Frame(self.tabs, padding=16)
        self.dependencies = ttk.Frame(self.tabs, padding=16)
        self.logs = ttk.Frame(self.tabs, padding=12)
        for page, label in ((self.work, "工作台"), (self.results, "上传结果"),
                            (self.dependencies, "依赖设置"), (self.logs, "运行日志")):
            self.tabs.add(page, text=label)
        self._work_page()
        self._results_page()
        self._dependency_page()
        self.log_text = tk.Text(self.logs, bg=CARD, fg=INK, relief="flat", wrap="word",
                                font=("Consolas", 10), state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(self.logs, command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        bottom = ttk.Frame(main, padding=(0, 14, 0, 0))
        bottom.pack(fill="x")
        self.status = tk.StringVar(value="就绪")
        ttk.Label(bottom, textvariable=self.status).pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=160)
        self.progress.pack(side="right")

    def _work_page(self):
        bar = ttk.Frame(self.work)
        bar.pack(fill="x", pady=(0, 10))
        self.mutating_buttons = []
        for label, action in (("＋ 添加影片", self.add_videos), ("添加文件夹", self.add_folder),
                              ("移除所选", self.remove_videos), ("清空", self.clear_videos)):
            button = ttk.Button(bar, text=label, command=action)
            button.pack(side="left", padx=(0, 8))
            self.mutating_buttons.append(button)
        self.queue_label = tk.StringVar(value="0 部影片")
        ttk.Label(bar, textvariable=self.queue_label, style="Muted.TLabel").pack(side="right")
        area = ttk.Frame(self.work)
        area.pack(fill="both", expand=True)
        self.video_tree = ttk.Treeview(area, columns=("name", "size", "path"), show="headings", height=6)
        for key, title, width in (("name", "影片", 260), ("size", "大小", 95), ("path", "完整路径", 540)):
            self.video_tree.heading(key, text=title)
            self.video_tree.column(key, width=width, minwidth=70)
        self.video_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(area, command=self.video_tree.yview)
        scroll.pack(side="right", fill="y")
        self.video_tree.configure(yscrollcommand=scroll.set)
        options = ttk.LabelFrame(self.work, text="截图设置", padding=12)
        options.pack(fill="x", pady=14)
        self.mode = tk.StringVar(value=next(k for k, v in MODES.items() if v == self.defaults.mode))
        self.count = tk.StringVar(value=str(self.defaults.count))
        self.cols = tk.StringVar(value=str(self.defaults.cols))
        self.rows = tk.StringVar(value=str(self.defaults.rows))
        self.width = tk.StringVar(value=str(self.defaults.width))
        ttk.Label(options, text="输出类型").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.mode_box = ttk.Combobox(options, textvariable=self.mode, values=list(MODES), state="readonly", width=16)
        self.mode_box.grid(row=0, column=1, sticky="w", padx=(0, 24))
        self.mode_box.bind("<<ComboboxSelected>>", lambda _: self._mode_changed())
        ttk.Label(options, text="每部截图张数").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.count_box = ttk.Spinbox(options, from_=1, to=100, textvariable=self.count, width=6)
        self.count_box.grid(row=0, column=3, sticky="w")
        ttk.Label(options, text="PNG · 保持原始画面尺寸", style="Muted.TLabel").grid(row=0, column=4, sticky="w", padx=18)
        ttk.Label(options, text="拼图布局").grid(row=1, column=0, sticky="w", pady=(14, 0))
        grid = ttk.Frame(options)
        grid.grid(row=1, column=1, sticky="w", pady=(14, 0))
        self.col_box = ttk.Spinbox(grid, from_=1, to=12, textvariable=self.cols, width=4)
        self.col_box.pack(side="left")
        ttk.Label(grid, text=" 列 × ").pack(side="left")
        self.row_box = ttk.Spinbox(grid, from_=1, to=12, textvariable=self.rows, width=4)
        self.row_box.pack(side="left")
        ttk.Label(grid, text=" 行").pack(side="left")
        ttk.Label(options, text="拼图目标宽度").grid(row=1, column=2, sticky="w", pady=(14, 0))
        self.width_box = ttk.Spinbox(options, from_=320, to=16384, increment=320, textvariable=self.width, width=8)
        self.width_box.grid(row=1, column=3, sticky="w", pady=(14, 0))
        ttk.Label(options, text="px · 网格取整可能相差数像素", style="Muted.TLabel").grid(row=1, column=4, sticky="w", padx=18, pady=(14, 0))
        upload = ttk.Frame(self.work)
        upload.pack(fill="x", pady=(0, 12))
        self.upload = tk.BooleanVar(value=self.defaults.upload)
        self.upload_check = ttk.Checkbutton(upload, text="截图后自动上传 Pixhost", variable=self.upload, command=self._action_label)
        self.upload_check.pack(side="left")
        ttk.Label(upload, text="内容分类").pack(side="left", padx=(28, 8))
        self.content = tk.StringVar(value="普通内容" if self.defaults.content_type == 0 else "成人内容")
        self.content_box = ttk.Combobox(upload, textvariable=self.content, values=("普通内容", "成人内容"), state="readonly", width=12)
        self.content_box.pack(side="left")
        ttk.Label(upload, text="仅上传生成的图片，影片保留在本机", style="Muted.TLabel").pack(side="right")
        output = ttk.Frame(self.work)
        output.pack(fill="x", pady=(0, 12))
        ttk.Label(output, text="保存目录").pack(side="left", padx=(0, 10))
        self.output = tk.StringVar(value=self.output_default)
        self.output_entry = ttk.Entry(output, textvariable=self.output)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.output_button = ttk.Button(output, text="选择…", command=self.choose_output)
        self.output_button.pack(side="right")
        ttk.Label(self.work, text="超过 10MB 才调用 oxipng；优化后仍超限的图片会保留并标记，不缩小、不转为有损格式。",
                  style="Muted.TLabel", wraplength=940).pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(self.work)
        actions.pack(fill="x")
        self.start_button = ttk.Button(actions, text="开始截图并上传", style="Primary.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消任务", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=10)
        self.open_session_button = ttk.Button(actions, text="打开历史任务…", command=self.open_session)
        self.open_session_button.pack(side="right")
        self._mode_changed()
        self._action_label()

    def _results_page(self):
        toolbar = ttk.Frame(self.results)
        toolbar.pack(fill="x", pady=(0, 10))
        self.result_count = tk.StringVar(value="本次任务：0 张图片")
        ttk.Label(toolbar, textvariable=self.result_count).pack(side="left")
        self.retry_button = ttk.Button(toolbar, text="上传 / 重试未完成", command=self.retry, state="disabled")
        self.retry_button.pack(side="right")
        self.folder_button = ttk.Button(toolbar, text="打开本次文件夹", command=self.open_job_folder, state="disabled")
        self.folder_button.pack(side="right", padx=8)
        table_frame = ttk.Frame(self.results)
        table_frame.pack(fill="both", expand=True)
        self.result_tree = ttk.Treeview(table_frame, columns=("name", "dimensions", "size", "status", "url"),
                                       show="headings", height=6)
        for key, title, width in (("name", "图片", 220), ("dimensions", "分辨率", 110),
                                  ("size", "上传大小", 100), ("status", "状态", 160), ("url", "高清原图直链", 360)):
            self.result_tree.heading(key, text=title)
            self.result_tree.column(key, width=width, minwidth=75)
        self.result_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(table_frame, command=self.result_tree.yview)
        scroll.pack(side="right", fill="y")
        self.result_tree.configure(yscrollcommand=scroll.set)
        horizontal = ttk.Scrollbar(self.results, orient="horizontal", command=self.result_tree.xview)
        horizontal.pack(fill="x", pady=(0, 10))
        self.result_tree.configure(xscrollcommand=horizontal.set)
        self.result_tree.bind("<<TreeviewSelect>>", lambda _: self._selection())
        details = ttk.Frame(self.results)
        details.pack(fill="both", pady=(0, 10))
        preview_frame = ttk.Frame(details, width=292, height=174)
        preview_frame.pack(side="left", fill="y", padx=(0, 14))
        preview_frame.pack_propagate(False)
        self.preview = ttk.Label(preview_frame, text="选择图片查看预览", anchor="center",
                                 background="#e7edf7", foreground=MUTED)
        self.preview.pack(fill="both", expand=True)
        code = ttk.LabelFrame(details, text="本次所有已上传图片的 BBCode", padding=8)
        code.pack(side="left", fill="both", expand=True)
        self.bbcode = tk.Text(code, height=8, wrap="none", relief="flat", bg=CARD, fg=INK,
                              font=("Consolas", 10), state="disabled")
        self.bbcode.pack(fill="both", expand=True)
        self.detail = tk.StringVar(value="高清直链会校验 PNG 类型与原图分辨率。")
        ttk.Label(self.results, textvariable=self.detail, style="Muted.TLabel", wraplength=980).pack(anchor="w", pady=(0, 10))
        actions = ttk.Frame(self.results)
        actions.pack(fill="x")
        for title, callback, style in (
            ("一键复制全部 BBCode", lambda: self.copy_all(True), "Primary.TButton"),
            ("复制全部高清直链", lambda: self.copy_all(False), "TButton"),
            ("复制所选直链", self.copy_selected, "TButton"),
            ("打开所选图片", self.open_selected, "TButton"),
        ):
            ttk.Button(actions, text=title, command=callback, style=style).pack(side="left", padx=(0, 8))

    def _dependency_page(self):
        ttk.Label(self.dependencies, text="依赖程序", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Label(self.dependencies, text="优先使用本工具 tools/bin 中的程序，其次使用系统 PATH。也可为每一项指定路径。",
                  style="Muted.TLabel", wraplength=980).pack(anchor="w", pady=(8, 18))
        table = ttk.Frame(self.dependencies)
        table.pack(fill="x")
        table.columnconfigure(1, weight=1)
        self.tool_labels = {}
        self.tool_buttons = []
        for row, name in enumerate(TOOL_NAMES):
            ttk.Label(table, text=name, width=14).grid(row=row, column=0, sticky="w", pady=10)
            value = tk.StringVar()
            self.tool_labels[name] = value
            ttk.Label(table, textvariable=value, wraplength=640).grid(row=row, column=1, sticky="w", padx=12)
            select = ttk.Button(table, text="选择…", command=lambda n=name: self.choose_tool(n))
            select.grid(row=row, column=2, padx=5)
            reset = ttk.Button(table, text="自动", command=lambda n=name: self.reset_tool(n))
            reset.grid(row=row, column=3)
            self.tool_buttons.extend((select, reset))
        actions = ttk.Frame(self.dependencies)
        actions.pack(fill="x", pady=24)
        self.install_button = ttk.Button(actions, text="一键下载缺少的依赖", style="Primary.TButton", command=self.install)
        self.install_button.pack(side="left")
        ttk.Button(actions, text="重新检测", command=self.refresh_tools).pack(side="left", padx=12)
        ttk.Label(self.dependencies, text="下载使用锁定版本和 SHA-256 校验，安装位置仅为本工具目录。FFmpeg 下载包较大，已安装时直接复用。",
                  style="Muted.TLabel", wraplength=960).pack(anchor="w", pady=(0, 18))
        advanced = ttk.LabelFrame(self.dependencies, text="上传与优化", padding=14)
        advanced.pack(fill="x")
        self.optimization = tk.StringVar(value=str(self.defaults.optimization))
        self.thumbnail = tk.StringVar(value=str(self.defaults.thumbnail_size))
        ttk.Label(advanced, text="oxipng 等级").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(advanced, from_=0, to=6, width=6, textvariable=self.optimization).grid(row=0, column=1, padx=14)
        ttk.Label(advanced, text="0–6；等级越高耗时越长", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(advanced, text="图床缩略图尺寸").grid(row=1, column=0, sticky="w", pady=(14, 0))
        ttk.Spinbox(advanced, from_=150, to=500, width=6, textvariable=self.thumbnail).grid(row=1, column=1, padx=14, pady=(14, 0))
        ttk.Label(advanced, text="只影响图床缩略图，不影响返回的高清原图", style="Muted.TLabel").grid(row=1, column=2, sticky="w", pady=(14, 0))
        ttk.Label(self.dependencies, text="项目与接口文档", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(24, 8))
        links = ttk.Frame(self.dependencies)
        links.pack(fill="x")
        for title, url in (("Mosaic", "https://github.com/mosaicvideo/mosaic"),
                            ("oxipng", "https://github.com/oxipng/oxipng"),
                            ("Pixhost API", "https://pixhost.to/api/index.html")):
            ttk.Button(links, text=title, command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=(0, 10))

    def _mode_changed(self):
        mode = MODES[self.mode.get()]
        self.count_box.configure(state="normal" if mode != "sheet" else "disabled")
        for item in (self.col_box, self.row_box, self.width_box):
            item.configure(state="normal" if mode != "screenshots" else "disabled")

    def _action_label(self):
        self.start_button.configure(text="开始截图并上传" if self.upload.get() else "开始截图（仅本地）")

    def settings(self) -> Settings:
        try:
            value = Settings(mode=MODES[self.mode.get()], count=int(self.count.get()),
                cols=int(self.cols.get()), rows=int(self.rows.get()), width=int(self.width.get()),
                upload=self.upload.get(), content_type=0 if self.content.get() == "普通内容" else 1,
                optimization=int(self.optimization.get()), thumbnail_size=int(self.thumbnail.get()), tools=dict(self.custom))
        except (KeyError, ValueError) as exc:
            raise ShotError("截图张数、布局、宽度与优化等级请填写整数") from exc
        value.validate()
        return value

    def save_config(self):
        atomic_text(config_path(), json.dumps({"settings": asdict(self.settings()), "output": self.output.get()}, ensure_ascii=False, indent=2))

    def add_paths(self, paths):
        for path in paths:
            path = Path(path).resolve()
            if path.is_file() and path not in self.videos:
                self.videos.append(path)
        self._video_rows()

    def add_videos(self):
        if not self.busy:
            self.add_paths(filedialog.askopenfilenames(title="选择影片", filetypes=[("影片", " ".join("*" + e for e in sorted(VIDEO_EXTENSIONS))), ("所有文件", "*.*")]))

    def add_folder(self):
        if self.busy:
            return
        selected = filedialog.askdirectory(title="选择影片文件夹（包括子文件夹）")
        if selected:
            # Folder scanning is a worker operation too: network shares can be slow.
            def scan():
                found = []
                for path in Path(selected).rglob("*"):
                    if self.stop.is_set():
                        break
                    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                        found.append(path)
                return sorted(found)
            self._worker(scan, "scan")

    def _video_rows(self):
        self.video_tree.delete(*self.video_tree.get_children())
        for index, path in enumerate(self.videos):
            try:
                size = f"{path.stat().st_size / 1_000_000_000:.2f} GB"
            except OSError:
                size = "文件待检查"
            self.video_tree.insert("", "end", iid=str(index), values=(path.name, size, str(path)))
        self.queue_label.set(f"{len(self.videos)} 部影片")

    def remove_videos(self):
        if not self.busy:
            selected = {int(i) for i in self.video_tree.selection()}
            self.videos = [p for i, p in enumerate(self.videos) if i not in selected]
            self._video_rows()

    def clear_videos(self):
        if not self.busy:
            self.videos.clear()
            self._video_rows()

    def choose_output(self):
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            self.output.set(selected)

    def choose_tool(self, name):
        path = filedialog.askopenfilename(title=f"选择 {name}", filetypes=[("可执行程序", "*.exe"), ("所有文件", "*.*")])
        if path:
            self.custom[name] = path
            self.refresh_tools()

    def reset_tool(self, name):
        self.custom.pop(name, None)
        self.refresh_tools()

    def refresh_tools(self):
        found = discover_tools(self.base, self.custom)
        for name, var in self.tool_labels.items():
            var.set("已就绪  " + found[name] if name in found else "待安装 / 路径待修正")

    def _set_busy(self, active: bool):
        self.busy = active
        for button in self.mutating_buttons + self.tool_buttons + [self.start_button, self.install_button, self.output_button,
                                                                  self.open_session_button]:
            button.configure(state="disabled" if active else "normal")
        self.retry_button.configure(state="normal" if self.job and self.job.records and not active else "disabled")
        self.cancel_button.configure(state="normal" if active else "disabled")
        if active:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _worker(self, operation, kind="job"):
        if self.busy:
            return
        self.stop = threading.Event()
        self._set_busy(True)
        self.status.set("正在处理…")
        def run():
            try:
                result = operation()
                self.events.put((kind, result))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=run, name="ptshot-worker", daemon=True).start()

    def _pipeline(self):
        return Pipeline(root=self.base, stop=self.stop,
            log=lambda text: self.events.put(("log", text)),
            changed=lambda job: self.events.put(("changed", job)))

    def start(self):
        if self.busy:
            return
        try:
            settings = self.settings()
            if not self.videos:
                raise ShotError("请先添加影片")
            if not self.output.get().strip():
                raise ShotError("请选择保存目录")
            missing = [n for n in ("mosaic-cli", "ffmpeg", "ffprobe", "mediainfo")
                       if n not in discover_tools(self.base, self.custom)]
            if missing:
                self.tabs.select(self.dependencies)
                raise ShotError("请点击「一键下载缺少的依赖」：" + ", ".join(missing))
            self.save_config()
        except (ShotError, OSError) as exc:
            messagebox.showinfo("检查设置", str(exc), parent=self.root)
            return
        videos, output = list(self.videos), Path(self.output.get())
        self.job = None
        self.preview.configure(image="", text="等待图片生成")
        self.preview_image = None
        self._render_results()
        self.tabs.select(self.results)
        self._worker(lambda: self._pipeline().run(videos, output, settings))

    def install(self):
        custom = dict(self.custom)
        self.tabs.select(self.logs)
        self._worker(lambda: install_missing(self.base, custom, lambda s: self.events.put(("log", s)), self.stop), "installed")

    def cancel(self):
        self.stop.set()
        self.status.set("正在取消；当前网络请求结束后保存结果…")
        self.cancel_button.configure(state="disabled")

    def retry(self):
        if self.busy or not self.job or not self.job.records:
            return
        self.job.settings.tools = dict(self.custom)
        job = self.job
        self._worker(lambda: self._pipeline().resume(job))

    def open_session(self):
        selected = filedialog.askopenfilename(title="打开任务记录", filetypes=[("任务记录", "session.json"), ("JSON", "*.json")],
                                              initialdir=self.output.get())
        if not selected:
            return
        try:
            job = Job.load(Path(selected))
            job.save()
            self.job = job
            self._render_results()
            self.retry_button.configure(state="normal" if job.records else "disabled")
            self.tabs.select(self.results)
            self.status.set("已打开任务：" + str(job.directory))
        except (OSError, ValueError, TypeError, KeyError, ShotError) as exc:
            messagebox.showerror("打开任务", str(exc), parent=self.root)

    def _render_results(self):
        records = self.job.records if self.job else []
        selection = self.result_tree.selection()
        scroll = self.result_tree.yview()
        self.result_tree.delete(*self.result_tree.get_children())
        for i, record in enumerate(records):
            self.result_tree.insert("", "end", iid=str(i), values=(Path(record.original_path).name,
                f"{record.width} × {record.height}", f"{(record.upload_bytes or record.original_bytes) / 1_000_000:.2f} MB",
                STATES.get(record.status, record.status), record.direct_url or record.show_url))
        for item in selection:
            if self.result_tree.exists(item):
                self.result_tree.selection_add(item)
        if scroll:
            self.result_tree.yview_moveto(scroll[0])
        urls = self.job.successful_urls if self.job else []
        errors = sum(r.status in ("error", "oversize") for r in records)
        video_errors = len(self.job.errors) if self.job else 0
        self.result_count.set(f"本次任务：{len(records)} 张图片 · {len(urls)} 张已上传 · {errors} 张待处理 · {video_errors} 项截图错误")
        self.bbcode.configure(state="normal")
        self.bbcode.delete("1.0", "end")
        self.bbcode.insert("1.0", bbcode_for_urls(urls))
        self.bbcode.configure(state="disabled")
        self.folder_button.configure(state="normal" if self.job else "disabled")
        if self.job and self.job.errors:
            self.detail.set(self.job.errors[-1])

    def _record(self):
        selected = self.result_tree.selection()
        if self.job and selected and int(selected[0]) < len(self.job.records):
            return self.job.records[int(selected[0])]
        return None

    def _selection(self):
        record = self._record()
        if not record:
            return
        self.detail.set(record.error or record.direct_url or record.original_path)
        selected = record.upload_path or record.original_path
        if getattr(self, "_preview_path", None) == selected:
            return
        try:
            image = tk.PhotoImage(file=selected)
            ratio = max(1, math.ceil(max(image.width() / 280, image.height() / 156)))
            self.preview_image = image.subsample(ratio, ratio)
            self.preview.configure(image=self.preview_image, text="")
            self._preview_path = selected
        except (tk.TclError, OSError):
            self.preview.configure(image="", text="预览待加载")

    def copy_text(self, text):
        if not text:
            self.status.set("尚无已成功上传的高清直链")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()
        self.status.set(f"已复制到剪贴板 · {len(text.splitlines())} 张图片")

    def copy_all(self, code):
        urls = self.job.successful_urls if self.job else []
        self.copy_text(bbcode_for_urls(urls) if code else "\n".join(urls))

    def copy_selected(self):
        record = self._record()
        self.copy_text(record.direct_url if record and record.status == "uploaded" else "")

    def open_selected(self):
        record = self._record()
        if record:
            if record.direct_url:
                webbrowser.open(pixhost_url(record.direct_url, direct=True))
            else:
                self._open_path(Path(record.upload_path or record.original_path))

    def open_job_folder(self):
        if self.job:
            self._open_path(self.job.directory)

    def _open_path(self, path):
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                webbrowser.open(path.as_uri())
        except OSError as exc:
            self.status.set(str(exc))

    def _log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", datetime.now().strftime("%H:%M:%S  ") + text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._log(value)
                elif kind in ("changed", "job"):
                    self.job = value
                    self._render_results()
                    if kind == "job":
                        label = JOB_STATES.get(value.state, value.state)
                        self.status.set(f"{label} · {len(value.successful_urls)}/{len(value.records)} 张已上传 · 结果已自动保存")
                        if value.errors:
                            self.detail.set(value.errors[-1])
                elif kind == "scan":
                    self.add_paths(value)
                    self.status.set(f"扫描完成 · {len(value)} 部影片")
                elif kind == "installed":
                    self.refresh_tools()
                    self.status.set("全部依赖已就绪")
                    self.tabs.select(self.dependencies)
                elif kind == "error":
                    self._log(value)
                    self.status.set("处理失败 · " + value[:140])
                    if not self.closing:
                        messagebox.showerror("PT Shot", value, parent=self.root)
                elif kind == "done":
                    self._set_busy(False)
                    if self.job:
                        try:
                            atomic_text(self.job.directory / "run.log", self.log_text.get("1.0", "end-1c"))
                        except OSError:
                            pass
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def close(self):
        if self.busy:
            if not messagebox.askyesno("结束任务", "取消当前任务并保存已完成的结果后退出？", parent=self.root):
                return
            self.closing = True
            self.cancel()
            return
        try:
            self.save_config()
        except (OSError, ShotError):
            pass
        self.root.destroy()


def launch():
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    Application(root)
    root.mainloop()
