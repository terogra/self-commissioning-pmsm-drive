"""Windows executable launcher for the packaged Streamlit application."""

import os
from pathlib import Path
import sys

# Import the dashboard so PyInstaller follows the application's static imports.
# The module is side-effect free until main() is called by Streamlit.
from app import dashboard as _dashboard  # noqa: F401


def bundle_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def dashboard_path():
    return bundle_root()/"app"/"dashboard.py"


def main():
    from streamlit.web import bootstrap

    headless = os.environ.get("PMSM_HEADLESS", "").strip().lower() in {"1", "true", "yes"}
    port = int(os.environ.get("PMSM_PORT", "8501"))
    flags = {
        "server.address": "127.0.0.1",
        "server.port": port,
        "server.headless": headless,
        "browser.gatherUsageStats": False,
    }
    # The normal Streamlit CLI loads flag options before bootstrap.run().
    # Our packaged launcher calls bootstrap directly, so mirror that setup
    # explicitly; otherwise Streamlit falls back to its default port/headless
    # values even though the flags are passed to the watcher layer.
    bootstrap.load_config_options(flags)
    bootstrap.run(str(dashboard_path()), False, [], flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
