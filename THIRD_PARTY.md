# Third-party components

PT Shot invokes unmodified external CLI programs as separate processes.

| Component | License | Project / corresponding source |
| --- | --- | --- |
| Mosaic CLI 0.1.10 | MIT | https://github.com/mosaicvideo/mosaic/tree/v0.1.10 |
| oxipng 10.2.1 | MIT | https://github.com/oxipng/oxipng/tree/v10.2.1 |
| MediaInfo CLI / MediaInfoLib 26.10 | BSD-2-Clause, with component-specific notices | https://mediaarea.net/en/MediaInfo/License · https://github.com/MediaArea/MediaInfo/tree/v26.10 |
| FFmpeg / ffprobe 9.0.2 Gyan build | GPL-3.0-or-later; individual bundled libraries retain their licenses | https://www.gyan.dev/ffmpeg/builds/ · https://github.com/FFmpeg/FFmpeg/tree/946fcce07b |
| Python 3.14 | PSF License | https://www.python.org/downloads/source/ |
| Tcl / Tk 8.6 | Tcl/Tk license | https://www.tcl.tk/software/tcltk/license.html |
| PyInstaller bootloader 6.22.3 | GPL-2.0-or-later with bootloader exception | https://pyinstaller.org/en/stable/license.html |

Full upstream license notices for the external programs are retained in `tools/licenses/`.
The FFmpeg build's original `README.txt` records its build configuration and linked libraries.
The frozen Python runtime's license and Tcl/Tk license files are retained under `_internal/`.

Dependency downloads are pinned in `dependencies.lock.json`. If FFmpeg is already installed,
the build script records the exact reused executables' versions and SHA-256 hashes in
`BUNDLED_TOOLS.json`; its original license and README are copied from that installation.
Pixhost is a remote hosting service, not a bundled library; its API documentation is
https://pixhost.to/api/index.html.
