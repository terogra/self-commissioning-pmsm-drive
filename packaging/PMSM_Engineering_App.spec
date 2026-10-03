# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent

streamlit_datas, streamlit_binaries, streamlit_hiddenimports = collect_all("streamlit")

datas = list(streamlit_datas)
datas += [
    (str(ROOT/"app"/"dashboard.py"), "app"),
    (str(ROOT/"results"/"firmware_parity"/"parity_summary.json"), "results/firmware_parity"),
]

a = Analysis(
    [str(ROOT/"app"/"windows_launcher.py")],
    pathex=[str(ROOT)],
    binaries=streamlit_binaries,
    datas=datas,
    hiddenimports=streamlit_hiddenimports + ["app.dashboard", "app.presentation", "app.i18n"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PMSM Engineering App",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PMSM-Engineering-App",
)
