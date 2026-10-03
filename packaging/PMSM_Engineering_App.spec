# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

streamlit_datas, streamlit_binaries, streamlit_hiddenimports = collect_all("streamlit")

datas = list(streamlit_datas)
datas += [
    ("app/dashboard.py", "app"),
    ("results/firmware_parity/parity_summary.json", "results/firmware_parity"),
]

a = Analysis(
    ["app/windows_launcher.py"],
    pathex=["."],
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
