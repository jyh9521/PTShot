# Third-party components

PTShot invokes unmodified external CLI programs as separate processes.

| Component | License | Project / corresponding source |
| --- | --- | --- |
| Mosaic CLI 0.1.10 | MIT | https://github.com/mosaicvideo/mosaic/tree/v0.1.10 |
| oxipng 10.2.1 | MIT | https://github.com/oxipng/oxipng/tree/v10.2.1 |
| MediaInfo CLI / MediaInfoLib 26.10 | BSD-2-Clause, with component-specific notices | https://mediaarea.net/en/MediaInfo/License · https://github.com/MediaArea/MediaInfo/tree/v26.10 |
| FFmpeg / ffprobe 9.0.2 Gyan build | GPL-3.0-or-later; individual bundled libraries retain their licenses | https://www.gyan.dev/ffmpeg/builds/ · https://github.com/FFmpeg/FFmpeg/tree/946fcce07b |
| Python 3.14 | PSF License | https://www.python.org/downloads/source/ |
| Tcl / Tk 8.6 | Tcl/Tk license | https://www.tcl.tk/software/tcltk/license.html |
| PyInstaller bootloader 6.22.3 | GPL-2.0-or-later with bootloader exception | https://pyinstaller.org/en/stable/license.html |
| Electron 45.2.3 / Chromium | MIT / BSD and third-party notices | https://github.com/electron/electron/tree/v45.2.3 |
| M3 Expressive Web 1.8.0 | Apache-2.0 | https://github.com/kyra-labs/m3exp-web |
| Google Sans Flex | SIL OFL-1.1 | Bundled with m3e-tokens, full license retained |
| Material Symbols Rounded | Apache-2.0 | Bundled with m3e-tokens, full license retained |
| React 19.3.1 / React DOM | MIT | https://github.com/facebook/react |
| React Aria / React Stately / Motion | Apache-2.0 / MIT, as recorded in component notices | See THIRD_PARTY_LICENSES.txt in the package |

Full upstream license notices for the external programs are retained in `tools/licenses/`.
The FFmpeg build's original `README.txt` records its build configuration and linked libraries.
The frozen Python worker runtime's license is retained under `resources/worker/_internal/`.
The current desktop package does not use Tcl/Tk. Electron's original license and Chromium
notices remain in the portable directory. `THIRD_PARTY_LICENSES.txt` aggregates npm and font notices.

Dependency downloads are pinned in `dependencies.lock.json`. If FFmpeg is already installed,
the build script records the exact reused executables' versions and SHA-256 hashes in
`BUNDLED_TOOLS.json`; its original license and README are copied from that installation.
Pixhost is a remote hosting service, not a bundled library; its API documentation is
https://pixhost.to/api/index.html.
