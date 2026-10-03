"""Native Qt Windows x64 onedir product, with no console or web runtime."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
datas = [(str(root/"results/firmware_parity/parity_summary.json"), "results/firmware_parity")]
a = Analysis([str(root/"packaging/launcher.py")], pathex=[str(root)],
    binaries=[], datas=datas, hiddenimports=collect_submodules("src"),
    hookspath=[], runtime_hooks=[],
    excludes=["streamlit", "uvicorn", "flask", "fastapi", "pandas", "pyarrow", "tkinter", "PyQt5", "PyQt6",
              "PySide2", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    hooksconfig={"matplotlib": {"backends": ["Agg", "QtAgg"]}}, noarchive=False)
# Qt uses Windows' ICU API. An unrelated Poppler DLL on the build PATH can
# shadow System32/icuuc.dll with versioned ICU exports and break QtCore import.
# Resolve this OS component through Windows, never bundle an ambient ICU DLL.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != "icuuc.dll"]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PMSM-Commissioning-Workbench",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PMSM-Commissioning-Workbench")
