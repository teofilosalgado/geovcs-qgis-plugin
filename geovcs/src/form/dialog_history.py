import os

from qgis.core import Qgis, QgsApplication, QgsMessageLog
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QPoint, Qt
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QMenu,
    QMessageBox,
    QTreeWidgetItem,
)
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnectionManager
from geovcs.src.util import busy_cursor, refresh_version_manager_dock, safe_text

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_history.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogHistory(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.button_refresh.setIcon(QgsApplication.getThemeIcon("/mActionRefresh.svg"))
        self.table_commits.setWordWrap(False)
        self.table_commits.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.button_refresh.clicked.connect(self.refresh)
        self.tree_branches.itemSelectionChanged.connect(self._build_table_widget)
        self.tree_branches.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_branches.customContextMenuRequested.connect(self.show_context_menu)

        if not GeoVCSConnectionManager().is_connected:
            self.button_refresh.setEnabled(False)
            self.setWindowTitle("GeoVCS - History (not connected)")
            return

        self._build_tree_branches()

    def _report_error(self, title: str, exception: Exception):
        message = f"{type(exception).__name__}: {exception}"
        QgsMessageLog.logMessage(message, "GeoVCS", Qgis.MessageLevel.Critical)
        try:
            iface.messageBar().pushMessage(
                title, message, Qgis.MessageLevel.Critical, 10
            )
        except Exception:  # noqa: BLE001 - iface may be unavailable
            pass

    @staticmethod
    def _short_date(value) -> str:
        text = safe_text(value)
        return text[:-4] if len(text) > 4 else text

    def _build_tree_branches(self):
        try:
            with busy_cursor():
                branches = sorted(
                    GeoVCSConnectionManager().get_branches(),
                    key=lambda item: item.name or "",
                )
        except Exception as exception:  # noqa: BLE001 - keep the dialog usable
            self._report_error("GeoVCS - Unable to list branches", exception)
            self.tree_branches.clear()
            return

        self.tree_branches.blockSignals(True)
        try:
            self._populate_tree(branches)
        finally:
            self.tree_branches.blockSignals(False)

        # Load the commits for the branch that ended up selected.
        self._build_table_widget()

    def _populate_tree(self, branches):
        self.tree_branches.clear()
        self.tree_branches.setHeaderLabels(
            ["Name", "Hash", "Dirty?", "Creation Date", "Created By"]
        )
        nodes: dict[str, QTreeWidgetItem] = {}

        for branch in branches:
            path_parts = (branch.name or "").split("]")

            widget_item_data = [
                path_parts[-1],
                safe_text(branch.hash, 8),
                "Yes" if branch.dirty else "No",
                self._short_date(branch.latest_author_date),
                safe_text(branch.latest_author),
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

            # Store fully-qualified branch name
            item.setData(0, Qt.ItemDataRole.UserRole, branch.name)

            item.setExpanded(True)

        self.tree_branches.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        for i in range(5):
            self.tree_branches.resizeColumnToContents(i)

    def _build_table_widget(self):
        selected_items = self.tree_branches.selectedItems()
        selected_item: QTreeWidgetItem | None = next(iter(selected_items), None)
        if not selected_item:
            old_model = self.table_commits.model()
            self.table_commits.setModel(QStandardItemModel())
            if old_model is not None:
                old_model.deleteLater()
            return

        branch = selected_item.text(0)

        current_item = selected_item
        while current_item.parent() is not None:
            current_item = current_item.parent()
            branch = f"{current_item.text(0)}]{branch}"

        if self.table_commits.model():
            self.table_commits.model().clear()

        try:
            with busy_cursor():
                logs = list(GeoVCSConnectionManager().get_logs(branch))
        except Exception as exception:  # noqa: BLE001 - keep the dialog usable
            self._report_error("GeoVCS - Unable to load commit history", exception)
            return

        old_model = self.table_commits.model()
        model_commits = QStandardItemModel()
        model_commits.setHorizontalHeaderLabels(["Date", "Author", "Hash", "Message"])
        for log in logs:
            model_commits.appendRow(
                [
                    QStandardItem(self._short_date(log.date)),
                    QStandardItem(safe_text(log.committer)),
                    QStandardItem(safe_text(log.commit_hash, 8)),
                    QStandardItem(safe_text(log.message)),
                ]
            )
        self.table_commits.setModel(model_commits)
        if old_model is not None:
            old_model.deleteLater()
        self.table_commits.resizeColumnsToContents()
        self.table_commits.horizontalHeader().setStretchLastSection(True)

    def refresh(self):
        self._build_tree_branches()

    def _delete_branch(self, branch_name: str, branch_alias: str):
        result = QMessageBox.question(
            self,
            f"GeoVCS - Delete Branch '{branch_alias}'",
            f"Are you sure you want to delete the branch '{branch_name}'?\n\n"
            "Only fully merged branches can be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            with busy_cursor():
                GeoVCSConnectionManager().delete_branch(branch_name)
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            QgsMessageLog.logMessage(
                f"Failed to delete branch '{branch_name}': {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            QMessageBox.critical(
                self,
                "GeoVCS - Delete Branch Failed",
                f"Could not delete branch '{branch_name}':\n\n{exception}",
            )
            return

        try:
            iface.messageBar().pushMessage(
                "GeoVCS - Branch Deleted",
                f"Branch '{branch_name}' deleted successfully.",
                Qgis.MessageLevel.Success,
            )
        except Exception:  # noqa: BLE001 - iface may be unavailable
            pass

        # The dock keeps its own branch combo box. Refresh it immediately,
        # otherwise the deleted branch remains selectable and the next
        # checkout attempt fails against a branch that no longer exists.
        refresh_version_manager_dock()
        self.refresh()

    def show_context_menu(self, position: QPoint):
        item = self.tree_branches.itemAt(position)

        if item is None:
            return
        branch_alias: str = str(item.text(0))
        branch_name: str = str(item.data(0, Qt.ItemDataRole.UserRole))

        # Prevent current branch from being removed and/or edited
        if branch_name == GeoVCSConnectionManager().branch:
            return

        # Create the menu
        menu = QMenu(self)
        action_delete = menu.addAction(f"Delete '{branch_alias}' branch...")

        # Map local widget coordinates to global screen coordinates
        global_position = self.tree_branches.viewport().mapToGlobal(position)

        # Show the menu and capture the selected action
        selected_action = menu.exec(global_position)
        if selected_action == action_delete:
            self._delete_branch(branch_name, branch_alias)
