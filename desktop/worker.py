"""Compute off the GUI thread; only signals transfer results to Qt widgets."""

import logging
from PySide6.QtCore import QObject, Signal, Slot


class CommissioningWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service, configuration):
        super().__init__()
        self.service, self.configuration = service, configuration

    @Slot()
    def run(self):
        try:
            self.succeeded.emit(self.service.run(self.configuration))
        except Exception as exc:
            logging.exception("Commissioning worker failed")
            self.failed.emit(type(exc).__name__)
        finally:
            self.finished.emit()
