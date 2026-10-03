"""Windowed PyInstaller entry point; source entry is python -m app."""

import logging
import sys

if __name__ == "__main__":
    try:
        from desktop.main import main
    except Exception:
        from desktop.runtime import configure_logging
        log_path = configure_logging()
        logging.exception("Native runtime import failed")
        if "--smoke-report" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                "Uygulama başlatılamadı / Application could not start.\n"+str(log_path), "PMSM", 16)
        raise SystemExit(1)
    raise SystemExit(main())
