"""In-process portable launcher. sys.executable is an EXE, not Python here."""

import logging
import os
from pathlib import Path
import sys
import traceback

from app.runtime import dashboard_path


def launch_settings(environment):
    headless = environment.get("PMSM_HEADLESS", "0")
    if headless not in ("0", "1"):
        raise ValueError("PMSM_HEADLESS must be 0 or 1")
    port = int(environment.get("PMSM_PORT", "8501"))
    if not 1 <= port <= 65535:
        raise ValueError("PMSM_PORT must be between 1 and 65535")
    return {"server.address": "127.0.0.1", "server.port": port,
            "server.headless": headless == "1", "browser.gatherUsageStats": False,
            "global.developmentMode": False, "server.fileWatcherType": "none"}


def configure_streamlit(settings):
    from streamlit import config
    from streamlit.web import bootstrap
    # CLI normally performs this BEFORE bootstrap.run; run itself does not
    # apply initial flags. Check actual options, not just a printed settings dict.
    bootstrap.load_config_options(flag_options=settings)
    for name, value in settings.items():
        if config.get_option(name) != value:
            raise RuntimeError(f"Streamlit configuration mismatch: {name}")


def main():
    log_directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))/"PMSMEngineering/logs"
    try:
        handlers = [logging.StreamHandler()]
        try:
            log_directory.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_directory/"startup.log", encoding="utf-8"))
        except OSError as exc:
            print(f"Startup log unavailable ({log_directory}): {exc}", file=sys.stderr)
        logging.basicConfig(level=logging.INFO, handlers=handlers)
        settings = launch_settings(os.environ)
        configure_streamlit(settings)
        script = dashboard_path()
        if not script.is_file():
            raise FileNotFoundError(f"Missing packaged dashboard: {script}")
        # Validate dynamically executed UI dependencies and committed data before
        # opening a browser. HTTP readiness must not conceal a missing dashboard.
        from app import dashboard
        from app.presentation import load_committed_parity_evidence
        from src.version import __version__
        evidence = load_committed_parity_evidence()
        logging.info("PMSM %s; resources=%s; M18 samples=%s; bind=127.0.0.1:%s; headless=%s",
            __version__, script.parent.parent, evidence["compared_samples"], settings["server.port"], settings["server.headless"])
        from streamlit.web import bootstrap
        # Direct bootstrap: never recursively launch this frozen executable as
        # though it were `python -m streamlit`.
        bootstrap.run(str(script), False, [], settings)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        logging.exception("PMSM startup failed; log=%s", log_directory/"startup.log")
        if not os.environ.get("PMSM_HEADLESS") == "1" and sys.stdin and sys.stdin.isatty():
            input("Başlatma hatası / Startup error. Enter: kapat / close. ")
        return 1


if __name__ == "__main__": raise SystemExit(main())
