import os

from qgis.core import (
    QgsApplication,
)
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QAbstractItemView, QDialog, QTreeWidgetItem

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnectionManager

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_history.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogHistory(QDialog, FORM_CLASS):
    def __init__(self, parent_path=None):
        super().__init__(parent_path)
        self.setupUi(self)

        self.button_refresh.setIcon(QgsApplication.getThemeIcon("/mActionRefresh.svg"))
        self.table_commits.setWordWrap(False)
        self.table_commits.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        if not GeoVCSConnectionManager().is_connected:
            return

        self.button_refresh.clicked.connect(self.refresh)
        self.tree_branches.itemSelectionChanged.connect(self._build_table_widget)
        self._build_tree_widget()

    def _build_tree_widget(self):
        self.tree_branches.clear()
        self.tree_branches.setHeaderLabels(
            ["Name", "Hash", "Dirty?", "Creation Date", "Created By"]
        )
        nodes: dict[str, QTreeWidgetItem] = {}

        sorted_branches = sorted(
            GeoVCSConnectionManager().get_branches(), key=lambda item: item.name
        )
        for branch in sorted_branches:
            path_parts = branch.name.split("]")

            widget_item_data = [
                path_parts[-1],
                branch.hash[:8],
                "Yes" if branch.dirty else "No",
                branch.latest_author_date[:-4],
                branch.latest_author,
            ]

            if len(path_parts) == 1:
                # Create root element (main branch)
                item = QTreeWidgetItem(self.tree_branches, widget_item_data)
                nodes[branch.name] = item
            else:
                # Create child elements
                parent_path = "]".join(path_parts[:-1])
                if parent_path in nodes:
                    parent_item = nodes[parent_path]
                    item = QTreeWidgetItem(parent_item, widget_item_data)
                    nodes[branch.name] = item
                else:
                    item = QTreeWidgetItem(self.tree_branches, widget_item_data)
                    nodes[branch.name] = item

            if branch.name == GeoVCSConnectionManager().branch:
                # Highlight current branch
                font = QFont()
                font.setBold(True)
                font.setUnderline(True)
                item.setFont(0, font)

                # Select current branch
                self.tree_branches.setCurrentItem(item)
                item.setSelected(True)

            item.setExpanded(True)

        self.tree_branches.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        for i in range(5):
            self.tree_branches.resizeColumnToContents(i)

    def _build_table_widget(self):
        selected_items = self.tree_branches.selectedItems()
        selected_item: QTreeWidgetItem | None = next(iter(selected_items), None)
        if not selected_item:
            return

        branch = selected_item.text(0)

        current_item = selected_item
        while current_item.parent() is not None:
            current_item = current_item.parent()
            branch = f"{current_item.text(0)}]{branch}"

        if self.table_commits.model():
            self.table_commits.model().clear()

        model_commits = QStandardItemModel()
        model_commits.setHorizontalHeaderLabels(["Date", "Author", "Message", "Hash"])
        for log in GeoVCSConnectionManager().get_logs(branch):
            model_commits.appendRow(
                [
                    QStandardItem(log.date[:-4]),
                    QStandardItem(log.committer),
                    QStandardItem(log.message),
                    QStandardItem(log.commit_hash[:8]),
                ]
            )
        self.table_commits.setModel(model_commits)
        self.table_commits.horizontalHeader().setStretchLastSection(True)
        self.table_commits.resizeColumnsToContents()

    def refresh(self):
        self._build_tree_widget()
