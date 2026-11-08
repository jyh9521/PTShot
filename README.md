# PT Shot · PT 截图工具

中文 Windows 桌面工具：**Mosaic 截图 → 超过 10MB 时 oxipng 无损优化 → Pixhost 上传 → 高清原图直链与一键复制 BBCode**。

## 直接使用

1. 解压 `PTShot-Windows-x64.zip`，双击 `PTShot/PTShot.exe`。整个文件夹一起保留。
2. 添加一部或多部影片，也可添加文件夹（递归查找常见影片格式）。
3. 选择「原尺寸截图」「总览拼图」或「截图 + 拼图」，设置截图张数 / 拼图布局及保存位置。
4. 点击「开始截图并上传」。默认每部影片均匀截取 6 张原尺寸 PNG。
5. 「上传结果」中点击 **一键复制全部 BBCode** 或 **复制全部高清直链**。

返回的是 `https://imgN.pixhost.to/images/...png` 这类高清原图直链，BBCode 为每张一行：

```text
[img]https://img3.pixhost.to/images/目录/图片.png[/img]
[img]https://img3.pixhost.to/images/目录/另一张.png[/img]
```

本地源码也可双击 `启动工具.cmd`，或使用 Python 3.11+：

```powershell
python -m ptshot
```

程序本身仅使用 Python 标准库（包含 Tkinter），无需 pip 安装运行依赖。打包版自带 Python/Tkinter 和截图工具，不要求安装 Python。

## 大图处理与画质

- 阈值严格为 **10,000,000 字节**；等于阈值不压缩，大于阈值才调用 oxipng。
- Mosaic 生成 PNG；原尺寸截图不在本工具中缩放。HDR 的映射由 Mosaic 自身处理。
- oxipng 在**副本**上运行 `-o 4 --strip safe --timeout 120`，保留原始 PNG；不启用 `--alpha`、`--scale16` 等会改变像素数据的选项。
- 上传明确指定 `optimize_for_web=0`，不请求 Pixhost 的有损 WebP 转换或尺寸缩减。
- 无损优化后仍大于 10MB：这张图片标记超限、跳过上传，其余图片继续。原图和优化副本都保留。拼图可降低目标宽度后重新生成；单张原尺寸截图不做静默降质。
- 拼图含时间戳、影片信息。目标宽度由 Mosaic 按偶数像素网格取整，实际可能小几像素；例如 1280px、2 列、10px 间距的实测输出为 1278px。

## 依赖与安装

截图引擎为上游 `mosaic-cli`，不是重新实现或改用 FFmpeg 代替 Mosaic。

| 依赖 | 锁定版本 | 用途 |
| --- | --- | --- |
| Mosaic CLI | 0.1.10 | 原尺寸 PNG / 总览拼图 |
| oxipng | 10.2.1 | 仅处理超限 PNG |
| FFmpeg / ffprobe | 下载包 9.0.2 essentials；已有安装可复用 | Mosaic 所需的解码与影片分析 |
| MediaInfo CLI | 26.10 | Mosaic 所需的媒体信息 |

「依赖设置」支持自动检测、指定每个程序路径，以及**一键下载缺少的依赖**（Windows x64）。下载版本与 SHA-256 写在 `dependencies.lock.json`，只安装到工具自身的 `tools/bin`，不修改系统 PATH。GitHub 下载不畅时，oxipng 可用同版本官方 GitHub Assets API 下载，仍校验相同 SHA-256。

发现顺序：明确指定的路径 → 工具目录 → 系统 PATH。明确指定的路径失效时会提示修正，不悄悄替换。Mosaic 使用随工具提供的独立 TOML 配置，避免污染或继承已有全局配置。

## 每次任务的文件

输出目录下按时间创建独立的 `PTShot-年月日-时分秒-微秒` 文件夹：

```text
originals/      原始截图，按影片与输出类型分目录
optimized/      仅超 10MB 时产生的优化副本
session.json    每张图片的路径、大小、尺寸、状态、展示页与原图直链
urls.txt        本次成功上传的全部高清原图直链
bbcode.txt      本次成功上传的全部 [img]高清原图直链[/img]
run.log         桌面端运行日志
```

同名影片在不同文件夹中也分别保存，不相互覆盖。每一步完成后原子保存任务记录与结果；界面可以打开历史 `session.json` 并点击「上传 / 重试未完成」。已成功的图片会跳过；API 已返回展示页但后续解析失败的图片只重新解析，不重复上传。

取消会终止 Mosaic / oxipng 及其子进程，并保留已完成的结果。进行中的网络请求使用 90 秒超时；收到的上传回执会先保存再响应取消。被取消或失败的**截图阶段**需重新开始该影片，历史任务重试仅处理已经登记的图片。

上传 POST 不做自动重试，以免响应丢失造成重复上传。若网络在上传成功但收到回执之前中断，显式重试可能再次上传该图片。原图直链由展示页 HTML 中的实际原图解析，再核实返回 PNG 类型与本地图片尺寸，不通过替换缩略图域名猜测。

Pixhost API 无需 API Key。内容分类支持普通内容 (`content_type=0`) 与成人内容 (`1`)。只上传生成图片，不上传源影片。偏好设置存放于 `%APPDATA%/PTShot/settings.json`。

## 命令行

```powershell
python -m ptshot doctor
python -m ptshot install-tools
python -m ptshot run "D:\影片\movie.mkv" --count 6 --output "D:\截图"
python -m ptshot run "D:\影片\movie.mkv" --mode both --cols 4 --rows 4 --width 3840 --no-upload
python -m ptshot resume "D:\截图\PTShot-...\session.json"
```

命令行结束会输出 `SESSION=...` 和 `RESULT state=... images=... uploaded=...`。全部完成退出码 0；部分失败、取消或配置错误退出码 1。`--no-upload` 仅截图与条件优化，后续可用 `resume` 上传。

## 开发与验证

```powershell
$env:PYTHONUTF8='1'
python -m unittest discover -v
python scripts/integration_smoke.py       # 合成影片，实际 Mosaic 与 >10MB 的 oxipng 分支
python scripts/integration_smoke.py --live # 仅将合成测试图片实际上传 Pixhost，并核对下载字节
python scripts/gui_smoke.py               # 需已有 build/live-smoke 实测任务；窗口、预览、实际剪贴板验证
python -m pip install -r requirements-build.txt
python scripts/build_windows.py
```

运行时集成使用固定的 subprocess 参数列表，不拼接 shell。网络 / 提取 / 优化在后台线程执行；Tk 只在主线程刷新。`ptshot/core.py` 为数据与格式契约，`network.py` 为 Pixhost 适配器，`pipeline.py` 编排步骤，`tools.py` 管理依赖，`gui.py` 与 `__main__.py` 分别提供图形和命令行入口。

## 上游文档

- [Mosaic 项目](https://github.com/mosaicvideo/mosaic)、[CLI 参数](https://mosaicvideo.github.io/cli.html)
- [oxipng 项目与说明](https://github.com/oxipng/oxipng)
- [Pixhost API v2](https://pixhost.to/api/index.html)
- [FFmpeg Windows 构建](https://www.gyan.dev/ffmpeg/builds/)、[MediaInfo CLI](https://mediaarea.net/en/MediaInfo/Download/Windows)

打包目录中的 `THIRD_PARTY.md` 与 `tools/licenses/` 记录随包依赖的许可证和来源。
