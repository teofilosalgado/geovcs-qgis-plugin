import os

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDialog,
)

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnectionManager

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_merge_branch.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogMergeBranch(QDialog, FORM_CLASS):
    def __init__(self, parent_path=None):
        super().__init__(parent_path)
        self.setupUi(self)

        self.table_commits.setWordWrap(False)
        self.table_commits.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.combo_destination_branch.setEnabled(False)
        self.combo_destination_branch.clear()
        self.combo_destination_branch.insertItem(0, GeoVCSConnectionManager().branch)
        self.combo_destination_branch.setCurrentIndex(0)

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
