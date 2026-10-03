"""Embed the existing engineering figures; never recreate their calculations."""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtWidgets import QVBoxLayout, QWidget
from app.localization import localize_figure


class PlotPanel(QWidget):
    def __init__(self, figure, parent=None):
        super().__init__(parent)
        self.canvas = FigureCanvasQTAgg(localize_figure(figure))
        self.canvas.setMinimumSize(640, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        layout.addWidget(self.canvas)
