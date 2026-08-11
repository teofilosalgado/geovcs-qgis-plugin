import os

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QAbstractItemView, QDialog, QHeaderView, QTreeWidgetItem

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnectionManager, GeoVCSDeltaAction

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_merge_branch.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogMergeBranch(QDialog, FORM_CLASS):
    def __init__(self, parent_path=None):
        super().__init__(parent_path)
        self.setupUi(self)

        self.splitter.setSizes([3, 4])

        self.table_commits.setWordWrap(False)
        self.table_commits.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_commits.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_commits.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.combo_destination_branch.setEnabled(False)
        self.combo_destination_branch.clear()
        self.combo_destination_branch.insertItem(0, GeoVCSConnectionManager().branch)
        self.combo_destination_branch.setCurrentIndex(0)

        self.tree_changes.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tree_changes.setHeaderLabels(
            ["Attribute", "Previous Value", "Current Value"]
        )

        self._update_source_branches()

    def _update_source_branches(self):
        if not GeoVCSConnectionManager().is_connected:
            return

        try:
            self.combo_source_branch.currentTextChanged.disconnect()
        except TypeError:
            pass

        self.combo_source_branch.clear()
        self.combo_source_branch.insertItem(0, "")
        self.combo_source_branch.setCurrentIndex(0)

        branches = sorted(
            GeoVCSConnectionManager().get_branches(),
            key=lambda item: item.name,
        )
        for index, branch in enumerate(branches):
            if GeoVCSConnectionManager().branch == branch.name:
                continue
            self.combo_source_branch.insertItem(index + 1, branch.name)

        self.combo_source_branch.currentTextChanged.connect(self.change_source_branch)
        QgsMessageLog.logMessage(
            f"Updated branches from '{GeoVCSConnectionManager().database}@{GeoVCSConnectionManager().host}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

    def change_source_branch(self):
        if self.combo_source_branch.currentIndex() == 0:
            if self.table_commits.model():
                self.table_commits.model().clear()
            self.tree_changes.clear()
            return

        source_branch = self.combo_source_branch.currentText()
        if not source_branch:
            return

        target_branch = GeoVCSConnectionManager().branch
        if not target_branch:
            return

        self._update_commits(source_branch, target_branch)

    def _update_commits(self, source_branch: str, target_branch: str):
        if self.table_commits.model():
            self.table_commits.model().clear()

        model_commits = QStandardItemModel()
        model_commits.setHorizontalHeaderLabels(["Date", "Author", "Hash", "Message"])
        for log in GeoVCSConnectionManager().get_logs(
            target_branch,
            source_branch,
        ):
            hash_item = QStandardItem(log.commit_hash[:8])
            hash_item.setData(log.commit_hash, Qt.ItemDataRole.UserRole)
            model_commits.appendRow(
                [
                    QStandardItem(log.date[:-4]),
                    QStandardItem(log.committer),
                    hash_item,
                    QStandardItem(log.message),
                ]
            )
        self.table_commits.setModel(model_commits)
        self.table_commits.resizeColumnsToContents()
        self.table_commits.horizontalHeader().setStretchLastSection(True)
        self.table_commits.selectionModel().currentRowChanged.connect(self.get_changes)
        QgsMessageLog.logMessage(
            f"Updated commits from branch '{source_branch}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

    def get_changes(self, current, previous):
        if not current.isValid():
            return

        commit = self.table_commits.model().data(
            self.table_commits.model().index(current.row(), 2),
            Qt.ItemDataRole.UserRole,
        )
        if not commit:
            return

        self.tree_changes.clear()

        table_diffs = GeoVCSConnectionManager().get_diffs(commit)
        for table_diff in table_diffs:
            # --- Level 1: Table ---
            table_node = QTreeWidgetItem(self.tree_changes)
            table_node.setText(0, table_diff.table_name)

            for feature_delta in table_diff.feature_deltas:
                # --- Level 2: Feature (OBJECTID) and Action ---
                feature_node = QTreeWidgetItem(table_node)

                action_icon = "❔"
                if feature_delta.action == GeoVCSDeltaAction.ADDED:
                    action_icon = "🟢"
                elif feature_delta.action == GeoVCSDeltaAction.MODIFIED:
                    action_icon = "🟡"
                elif feature_delta.action == GeoVCSDeltaAction.REMOVED:
                    action_icon = "🔴"

                feature_node.setText(
                    0,
                    f"{action_icon} {feature_delta.objectid}: {feature_delta.action.name}",
                )

                for attribute_delta in feature_delta.attribute_deltas:
                    # --- Level 3: Attribute Values ---
                    attribute_node = QTreeWidgetItem(feature_node)
                    attribute_node.setText(0, attribute_delta.name)

                    previous_text = (
                        str(attribute_delta.from_value)
                        if attribute_delta.from_value is not None
                        else ""
                    )
                    current_text = (
                        str(attribute_delta.to_value)
                        if attribute_delta.to_value is not None
                        else ""
                    )

                    attribute_node.setText(1, previous_text)
                    attribute_node.setText(2, current_text)

        # Automatically expand the Table and Features (Levels 1 and 2)
        self.tree_changes.expandToDepth(1)
        self.tree_changes.header().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree_changes.header().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )

        QgsMessageLog.logMessage(
            f"Updated changes from commit '{commit}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
