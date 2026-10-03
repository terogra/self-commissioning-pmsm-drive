"""Windows x64 onedir build; source/static resources retain repository layout."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas, binaries, hiddenimports = collect_all("streamlit")
datas += copy_metadata("streamlit", recursive=True)
datas += [(str(p), "app") for p in (root/"app").glob("*.py")]
datas += [(str(root/"results/firmware_parity/parity_summary.json"), "results/firmware_parity")]
hiddenimports += collect_submodules("app") + collect_submodules("src") + collect_submodules("experiments")
hiddenimports += collect_submodules("uvicorn")
a = Analysis([str(root/"packaging/launcher.py")], pathex=[str(root)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], runtime_hooks=[], excludes=["tkinter"],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}}, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PMSM Engineering App",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PMSM Engineering App")
