# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)

pil_datas, pil_binaries, pil_hiddenimports = collect_all("PIL")

if sys.platform == "win32":
    INPUT_HIDDENIMPORTS = ["pynput.keyboard._win32", "pynput.mouse._win32"]
elif sys.platform.startswith("linux"):
    INPUT_HIDDENIMPORTS = ["pynput.keyboard._xorg", "pynput.mouse._xorg"]
else:
    INPUT_HIDDENIMPORTS = []

HIDDENIMPORTS = INPUT_HIDDENIMPORTS + pil_hiddenimports + ["PIL._tkinter_finder", "PIL.ImageTk"]

a = Analysis(
    [str(ROOT / "src" / "main.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=pil_binaries,
    datas=[
        (str(ROOT / "public" / "assets" / "mixput.ico"), "public/assets"),
        (str(ROOT / "public" / "assets" / "mixput-ico.png"), "public/assets"),
        (str(ROOT / "public" / "assets" / "mixput.png"), "public/assets"),
        (str(ROOT / "public" / "assets" / "drawing-1.svg"), "public/assets"),
    ] + pil_datas,
    hiddenimports=HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mixput",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "public" / "assets" / "mixput.ico") if sys.platform == "win32" else None,
)