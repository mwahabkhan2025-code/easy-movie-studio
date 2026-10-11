# PyInstaller spec: builds a single Windows .exe for Easy Movie Studio.
#
# Build (from the project root, with the venv from requirements.txt active and
# PyInstaller installed -- `pip install pyinstaller`):
#
#     python scripts\build_icon.py            (once, or after the icon design changes)
#     pyinstaller easy_movie_studio.spec
#
# The result is dist\EasyMovieStudio\EasyMovieStudio.exe (a one-folder build, not --onefile --
# a single-folder build starts much faster, which matters more for an editor the person
# keeps open than shaving the installer down to one file). See README.md's "Packaging"
# section for what still has to be placed next to the .exe (a full FFmpeg build).

import os

block_cipher = None
root = os.path.abspath(os.path.dirname(__file__))

# qtawesome ships its Material Design Icons font + a JSON glyph map as package data;
# PyInstaller's import analysis finds the Python it imports but not these non-Python
# resources, so they're collected explicitly (collect_data_files handles both the
# installed-package and the editable-install layouts).
try:
    from PyInstaller.utils.hooks import collect_data_files
    qtawesome_data = collect_data_files("qtawesome")
except Exception:
    qtawesome_data = []

# imageio-ffmpeg bundles a real platform ffmpeg.exe as package data (not a Python
# import), so it needs the same explicit treatment, or a packaged build falls back to
# the "not found" message at runtime despite the dependency being installed.
try:
    imageio_ffmpeg_data = collect_data_files("imageio_ffmpeg")
except Exception:
    imageio_ffmpeg_data = []

a = Analysis(
    ["easy_movie_studio/__main__.py"],
    pathex=[root],
    binaries=[],
    datas=qtawesome_data + imageio_ffmpeg_data,
    hiddenimports=[
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "sounddevice", "soundfile",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EasyMovieStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app -- no console window
    icon=os.path.join(root, "build", "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="EasyMovieStudio",
)
