"""Source/frozen resource and diagnostic paths, independent of working directory."""

import logging
import os
from pathlib import Path
import tempfile


def resource_root():
    return Path(__file__).resolve().parents[1]


def configure_logging():
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))/"PMSMCommissioningWorkbench/logs"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        root = Path(tempfile.gettempdir())/"PMSMCommissioningWorkbench/logs"
        root.mkdir(parents=True, exist_ok=True)
    path = root/"desktop.log"
    logging.basicConfig(filename=path, encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)
    return path
