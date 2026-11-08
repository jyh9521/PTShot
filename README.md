# PTShot

**影片截图 → 超限无损优化 → Pixhost 高清直链 → 一键复制 BBCode。**

Windows 桌面界面采用 **Material 3 Expressive** 组件、语义色彩、形状变化与弹簧动效。
默认窗口 **1120 × 820**，只有截图、结果、设置三个导航入口。无功能装饰、设计体系标签和画质徽章已移除，开始按钮固定在底部。

项目地址：[github.com/jyh9521/PTShot](https://github.com/jyh9521/PTShot)。

## 使用

打包版：解压后双击 **`PTShot-M3E/PTShot.exe`**，整个文件夹一起保留。自带 Electron、Python 工作进程和 5 项引擎，不需要另装 Python 或 Node.js。

1. 添加影片 / 文件夹，也可以拖入影片文件。
2. 选择原图、拼图或两者，设置张数、保存目录和自动上传。
3. 点击「开始截图并上传」。
4. 结果页点击「复制全部 BBCode」或「复制全部直链」。

```text
[img]https://img3.pixhost.to/images/目录/图片.png[/img]
[img]https://img3.pixhost.to/images/目录/另一张.png[/img]
```

复制的是高清原图直链，不是缩略图或展示页。结果页也可预览、打开本地图片，或打开历史 `session.json` 重试未完成图片。

## 截图与画质

- 真正调用上游 **Mosaic CLI 0.1.10**。默认每部影片均匀截取 6 张原尺寸 PNG，也支持带时间戳和影片信息的总览拼图。
- 图片 **大于 10,000,000 字节**时才调用 **oxipng 10.2.1**，等于阈值不优化。
- 在副本上使用 `-o 4 --strip safe --timeout 120` 无损优化，不改源影片和原始 PNG，不启用 `--alpha` 或 `--scale16`。
- 上传明确指定 `optimize_for_web=0`，不请求图床的有损 WebP 转换或尺寸缩减。
- 优化后仍超限：保留图片、标记超限、继续其余图片。不静默缩小或转成有损格式。
- 高清地址从 API 返回的展示页中解析，再校验返回 PNG 类型及原始尺寸。不通过替换缩略图域名猜测。
- 拼图宽度由 Mosaic 对网格取整，可能比目标小几像素。例如目标 1280px、2 列、10px 间距的实测输出为 1278px。

## 保存与续传

每次创建独立任务文件夹，同名影片按来源分目录，不相互覆盖：

```text
originals/       原始截图
optimized/       仅超 10 MB 时生成的优化副本
session.json     每张图片的状态、尺寸、展示页和高清直链
urls.txt         本次成功上传的全部高清直链
bbcode.txt       本次成功上传的全部 BBCode
run.log          运行日志
```

任务和导出文件每一步原子保存。历史任务会跳过已上传图片；有展示页回执但原图解析失败时，只重试解析，不重复上传。

上传 POST 不自动重试，避免响应丢失造成重复上传。若服务端已上传但回执尚未收到时断网，显式重试可能再次上传。
取消会终止截图 / 优化子进程并保存已有结果；网络请求使用 90 秒超时，收到回执后会先保存再响应取消。
历史重试只处理已登记图片，失败或取消的截图阶段可重新添加该影片。

Pixhost 无需 API Key。普通内容和成人内容分类在设置页选择。只上传生成图片，不上传源影片。

## 依赖

依赖设置支持单独选择程序、重新检测和一键安装缺少的依赖。

| 程序 | 版本 / 作用 |
| --- | --- |
| Mosaic CLI | 0.1.10，截图与拼图 |
| oxipng | 10.2.1，超限 PNG 无损优化 |
| FFmpeg / ffprobe | 自动下载锁定 9.0.2 essentials，已有安装可复用 |
| MediaInfo CLI | 26.10，影片元数据 |

下载来源与 SHA-256 固定在 `dependencies.lock.json`。只安装到工具目录，不修改系统 PATH。
优先级：明确指定路径 → 工具目录 → PATH。Mosaic 使用独立 TOML 配置。

## 开发

需要 **Node.js 24、Python 3.11+**。Python 工作进程只使用标准库。

```powershell
npm ci
python scripts/prepare_electron.py
python -m ptshot install-tools
npm start
```

已有构建时也可双击 `启动工具.cmd` 或运行 `python -m ptshot`。打包版优先启动新界面，不再启动 Tkinter。

```powershell
$env:PYTHONUTF8='1'
python -m unittest discover -v
npm run build
npx playwright install chromium
npm test
python scripts/integration_smoke.py        # 实际 Mosaic 与 >10MB oxipng 分支
python scripts/integration_smoke.py --live # 仅上传合成测试图，并比较下载字节
npm run test:desktop                      # 真实桌面截图、预览和剪贴板；需本地集成测试样例
```

Windows 打包：

```powershell
python -m pip install -r requirements-build.txt
npm run package:win
node scripts/desktop_smoke.mjs --packaged --live
python scripts/archive_windows.py
```

`dist/PTShot-M3E/` 为自包含目录，归档为 `dist/PTShot-0.2.0-Windows-x64.zip`。
归档前检查空间，完整重开并校验 ZIP 后再替换旧包。打包时只合并更新程序文件，不递归删除用户输出目录。

命令行批处理仍可独立使用：

```powershell
python -m ptshot doctor
python -m ptshot run "D:\影片\movie.mkv" --count 6 --output "D:\截图"
python -m ptshot run "D:\影片\movie.mkv" --mode both --cols 4 --rows 4 --width 3840 --no-upload
python -m ptshot resume "D:\截图\PTShot-...\session.json"
```

## 实现

- `frontend/`：React + M3 Expressive Web 1.8.0，所有字体和图标本地打包。
- `desktop/`：Electron 45.2.3，本地受隔离的界面与窄 IPC 接口，不开启 HTTP 服务。
- `ptshot/bridge.py`：JSON-lines 工作进程，传递任务进度和取消事件。
- `ptshot/core.py` / `pipeline.py` / `network.py` / `tools.py`：数据契约、编排、Pixhost 和依赖管理。
- [设计说明](docs/MATERIAL_3_EXPRESSIVE.md)：规范参考与组件来源。M3 Expressive Web 是独立实现，不是 Google 产品。
- [第三方组件](THIRD_PARTY.md)，打包版也包含完整许可证。

上游文档：[Mosaic](https://github.com/mosaicvideo/mosaic)、[CLI](https://mosaicvideo.github.io/cli.html)、[oxipng](https://github.com/oxipng/oxipng)、[Pixhost API](https://pixhost.to/api/index.html)。
