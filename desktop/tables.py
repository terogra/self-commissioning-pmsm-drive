"""Read-only native tables keep raw row values separate from display precision."""

from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtWidgets import QHeaderView, QTableView
from app.localization import t


class ResultTableModel(QAbstractTableModel):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = tuple(rows)
        self.columns = tuple(rows[0]) if rows else ()

    def rowCount(self, parent=None): return len(self.rows)
    def columnCount(self, parent=None): return len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        value = self.rows[index.row()][self.columns[index.column()]]
        if role == Qt.ItemDataRole.UserRole: return value
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if value is None: return t("unavailable")
            if isinstance(value, str): return t(value)
            if isinstance(value, float): return f"{value:.9g}" if role == Qt.ItemDataRole.DisplayRole else repr(value)
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (float, int)):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return t(self.columns[section]) if orientation == Qt.Orientation.Horizontal else str(section+1)


def result_table(rows):
    table = QTableView()
    table.setModel(ResultTableModel(rows, table))
    table.setAlternatingRowColors(True)
    table.setWordWrap(True)
    table.verticalHeader().setDefaultSectionSize(38)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setDefaultSectionSize(135)
    table.setMinimumHeight(150)
    return table
