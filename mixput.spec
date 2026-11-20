# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "src" / "main.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "public" / "assets" / "mixput.ico"), "public/assets"),
        (str(ROOT / "public" / "assets" / "mixput-ico.png"), "public/assets"),
        (str(ROOT / "public" / "assets" / "mixput.png"), "public/assets"),
        (str(ROOT / "public" / "assets" / "drawing-1.svg"), "public/assets"),
    ],
    hiddenimports=INPUT_HIDDENIMPORTS,
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
