"""Initialize the Qt application from source or the Windows package."""

import argparse
import json
import logging
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop.main_window import MainWindow
from desktop.runtime import configure_logging
from src.version import __version__


FORBIDDEN_RUNTIME_PREFIXES = ("streamlit", "uvicorn", "flask", "fastapi", "PySide6.QtWebEngine")


def runtime_report(window):
    return {"qt_window_initialized": True, "window_visible": window.isVisible(),
        "window_title": window.windowTitle(), "qt_platform": QApplication.platformName(),
        "version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
        "forbidden_runtime_modules": sorted(name for name in sys.modules
            if name.startswith(FORBIDDEN_RUNTIME_PREFIXES))}


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-report", type=Path, help="Initialize the real Qt window and exit with a diagnostic report")
    parser.add_argument("--capture-demo", type=Path, help="Capture the actual default commissioning window after a real run")
    args = parser.parse_args(arguments)
    application = QApplication.instance() or QApplication([sys.argv[0]])
    application.setApplicationName("PMSM-Commissioning-Workbench")
    application.setApplicationVersion(__version__)
    try:
        log_path = configure_logging()
        logging.info("Native Qt startup; frozen=%s; version=%s", bool(getattr(sys, "frozen", False)), __version__)
        window = MainWindow()
        window.show()
    except Exception:
        logging.exception("Native startup failed")
        if not args.smoke_report:
            QMessageBox.critical(None, "PMSM", "Uygulama başlatılamadı / Application could not start.\nSee desktop.log.")
        return 1

    def exception_hook(exc_type, value, traceback):
        logging.error("Unhandled Qt callback", exc_info=(exc_type, value, traceback))
        window.show_error(exc_type.__name__)
    sys.excepthook = exception_hook

    if args.smoke_report:
        def record_startup():
            try:
                report = runtime_report(window)
                if report["forbidden_runtime_modules"]: raise RuntimeError("Unexpected web runtime import")
                report["log_path"] = str(log_path)
                args.smoke_report.parent.mkdir(parents=True, exist_ok=True)
                args.smoke_report.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
                window.close()
                application.exit(0)
            except Exception:
                logging.exception("Native smoke initialization failed")
                application.exit(1)
        QTimer.singleShot(250, record_startup)
    if args.capture_demo:
        def capture():
            if window.busy:
                QTimer.singleShot(100, capture)
                return
            if window.result is None or not window.result.quality.accepted:
                logging.error("Default capture run did not complete accepted commissioning")
                application.exit(1)
                return
            window.tabs.setCurrentIndex(1)
            args.capture_demo.parent.mkdir(parents=True, exist_ok=True)
            QTimer.singleShot(250, lambda: window.grab().save(str(args.capture_demo)))
        window.run_completed.connect(lambda _: QTimer.singleShot(100, capture))
        QTimer.singleShot(0, window.start_commissioning)
    return application.exec()
