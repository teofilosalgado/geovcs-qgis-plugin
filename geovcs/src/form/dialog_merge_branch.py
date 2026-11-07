import os

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QMessageBox,
    QTreeWidgetItem,
)
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.form.dialog_merge_conflicts import GeoVCSDialogMergeConflicts
from geovcs.src.model import GeoVCSConnectionManager, GeoVCSDeltaAction
from geovcs.src.util import busy_cursor, safe_text

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_merge_branch.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogMergeBranch(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._target_branch: str | None = GeoVCSConnectionManager().branch
        self._source_branch: str | None = None

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
        self.combo_destination_branch.insertItem(0, self._target_branch or "")
        self.combo_destination_branch.setCurrentIndex(0)

        self.tree_changes.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tree_changes.setHeaderLabels(
            ["Attribute", "Previous Value", "Current Value"]
        )

        self.dialog_button_box.accepted.connect(self._accept)
        self.dialog_button_box.rejected.connect(self.reject)

        self._update_source_branches()

    @staticmethod
    def _notify(title: str, message: str, level):
        try:
            iface.messageBar().pushMessage(title, message, level)
        except Exception:  # noqa: BLE001 - notifications are best effort
            pass

    def _set_busy(self, busy: bool):
        self.dialog_button_box.setEnabled(not busy)
        self.combo_source_branch.setEnabled(not busy)
        self.check_delete_source_branch.setEnabled(not busy)
        self.table_commits.setEnabled(not busy)
        self.tree_changes.setEnabled(not busy)

    def _accept(self):
        if not self._source_branch or not self._target_branch:
            QMessageBox.warning(
                self,
                "GeoVCS - Merge Branch",
                "Please select a source branch to merge.",
            )
            return

        question_result = QMessageBox.question(
            self,
            "GeoVCS - Merge Branch",
            f"Are you sure you want to merge the branch '{self._source_branch}' "
            f"to '{self._target_branch}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if question_result != QMessageBox.StandardButton.Yes:
            return

        delete_source = self.check_delete_source_branch.isChecked()
        manager = GeoVCSConnectionManager()
        self._set_busy(True)
        try:
            with busy_cursor():
                merge_result = manager.merge(source_branch=self._source_branch)

            if not merge_result.conflicts:
                QgsMessageLog.logMessage(
                    f"Branch '{self._source_branch}' merged into '{self._target_branch}' "
                    f"successfully generating commit '{merge_result.hash}'.",
                    "GeoVCS",
                    Qgis.MessageLevel.Success,
                )
                self._notify(
                    "GeoVCS - Branch Merged",
                    f"Branch '{self._source_branch}' merged into '{self._target_branch}' successfully.",
                    Qgis.MessageLevel.Success,
                )
                self.accept()
                return

            QgsMessageLog.logMessage(
                f"Merge resulted in '{merge_result.conflicts}' conflicts: "
                f"{merge_result.message or 'unresolved conflicts'}",
                "GeoVCS",
                Qgis.MessageLevel.Warning,
            )
            conflict_tables = manager.get_conflict_tables()
            strategy, ok = GeoVCSDialogMergeConflicts.execute(conflict_tables, self)
            if not ok or not strategy:
                manager.abort_merge()
                QgsMessageLog.logMessage(
                    f"Merge between '{self._source_branch}' and '{self._target_branch}' was aborted.",
                    "GeoVCS",
                    Qgis.MessageLevel.Info,
                )
                QMessageBox.information(
                    self,
                    "GeoVCS - Merge Aborted",
                    "The merge operation was cancelled and all pending changes were aborted.",
                )
                return

            with busy_cursor():
                manager.resolve_conflicts(strategy, ".")
                commit_message = (
                    f"Merge branch '{self._source_branch}' into "
                    f"'{self._target_branch}' (resolved conflicts using {strategy})"
                )
                commit_hash = manager.add_all_and_commit(commit_message)

            QgsMessageLog.logMessage(
                f"Conflicts resolved using '{strategy}'. Commit '{commit_hash}' created.",
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )
            self._notify(
                "GeoVCS - Conflicts Resolved",
                f"Branch '{self._source_branch}' merged with conflicts resolved using {strategy}.",
                Qgis.MessageLevel.Success,
            )

            if delete_source:
                try:
                    with busy_cursor():
                        manager.delete_branch(self._source_branch)
                except Exception as exception:  # noqa: BLE001 - merge already succeeded
                    QMessageBox.warning(
                        self,
                        "GeoVCS - Source Branch Not Deleted",
                        f"The merge succeeded, but the source branch "
                        f"'{self._source_branch}' could not be deleted:\n\n{exception}",
                    )

            self.accept()
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            # A merge may have left the session with autocommit disabled and an
            # unresolved conflict state. Try to restore a clean session.
            if manager.merge_in_progress:
                try:
                    manager.abort_merge()
                except Exception:  # noqa: BLE001 - preserve the original error
                    pass

            QgsMessageLog.logMessage(
                f"Failed to merge branch '{self._source_branch}' into "
                f"'{self._target_branch}': {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            QMessageBox.critical(
                self,
                "GeoVCS - Merge Error",
                f"Failed to merge branch '{self._source_branch}' into "
                f"'{self._target_branch}':\n\n{exception}",
            )
        finally:
            self._set_busy(False)

    def _update_source_branches(self):
        if not GeoVCSConnectionManager().is_connected:
            self.combo_source_branch.setEnabled(False)
            return

        try:
            with busy_cursor():
                branches = sorted(
                    GeoVCSConnectionManager().get_branches(),
                    key=lambda item: item.name or "",
                )
        except Exception as exception:  # noqa: BLE001 - keep the dialog usable
            QgsMessageLog.logMessage(
                f"Unable to list source branches: {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            QMessageBox.critical(
                self,
                "GeoVCS - Merge Branch",
                f"Unable to list the available branches:\n\n{exception}",
            )
            self.combo_source_branch.setEnabled(False)
            return

        self.combo_source_branch.blockSignals(True)
        try:
            self.combo_source_branch.clear()
            self.combo_source_branch.insertItem(0, "")
            self.combo_source_branch.setCurrentIndex(0)
            for branch in branches:
                if GeoVCSConnectionManager().branch == branch.name:
                    continue
                self.combo_source_branch.insertItem(
                    self.combo_source_branch.count(), branch.name
                )
        finally:
            self.combo_source_branch.blockSignals(False)

        try:
            self.combo_source_branch.currentTextChanged.disconnect(
                self.on_change_source_branch
            )
        except TypeError:
            pass
        self.combo_source_branch.currentTextChanged.connect(
            self.on_change_source_branch
        )
        QgsMessageLog.logMessage(
            f"Updated branches from '{GeoVCSConnectionManager().database}@"
            f"{GeoVCSConnectionManager().host}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

    def on_change_source_branch(self):
        if self.combo_source_branch.currentIndex() == 0:
            self._source_branch = None
            old_model = self.table_commits.model()
            self.table_commits.setModel(QStandardItemModel())
            if old_model is not None:
                old_model.deleteLater()
            self.tree_changes.clear()
            self.setWindowTitle("GeoVCS - Merge Branch")
            return

        source_branch = self.combo_source_branch.currentText().strip()
        if not source_branch:
            return

        target_branch = GeoVCSConnectionManager().branch
        if not target_branch:
            return

        self._target_branch = target_branch
        self._source_branch = source_branch
        self.setWindowTitle(
            f"GeoVCS - Merge Branch '{source_branch}' > '{target_branch}'"
        )

        self._update_commits(source_branch, target_branch)

    def _short_date(self, value) -> str:
        text = safe_text(value)
        return text[:-4] if len(text) > 4 else text

    def _update_commits(self, source_branch: str, target_branch: str):
        try:
            with busy_cursor():
                logs = list(
                    GeoVCSConnectionManager().get_logs(
                        target_branch,
                        source_branch,
                    )
                )
        except Exception as exception:  # noqa: BLE001 - keep the dialog usable
            QgsMessageLog.logMessage(
                f"Unable to load commits between '{source_branch}' and "
                f"'{target_branch}': {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            QMessageBox.critical(
                self,
                "GeoVCS - Merge Branch",
                f"Unable to load the commits to merge:\n\n{exception}",
            )
            return

        QgsMessageLog.logMessage(
            f"Got '{len(logs)}' commits between target branch '{target_branch}' "
            f"and source branch '{source_branch}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

        old_model = self.table_commits.model()
        model_commits = QStandardItemModel()
        model_commits.setHorizontalHeaderLabels(["Date", "Author", "Hash", "Message"])

        for log in logs:
            hash_item = QStandardItem(safe_text(log.commit_hash, 8))
            hash_item.setData(log.commit_hash, Qt.ItemDataRole.UserRole)
            model_commits.appendRow(
                [
                    QStandardItem(self._short_date(log.date)),
                    QStandardItem(safe_text(log.committer)),
                    hash_item,
                    QStandardItem(safe_text(log.message)),
                ]
            )
        self.table_commits.setModel(model_commits)
        if old_model is not None:
            old_model.deleteLater()

        if not logs:
            return

        selection_model = self.table_commits.selectionModel()
        if selection_model is not None:
            selection_model.currentRowChanged.connect(
                self.on_change_current_selected_commit
            )
        self.table_commits.selectRow(0)

    def on_change_current_selected_commit(self, current, previous):
        if not current.isValid():
            return

        model = self.table_commits.model()
        if model is None:
            return

        commit = model.data(
            model.index(current.row(), 2),
            Qt.ItemDataRole.UserRole,
        )
        if not commit:
            return

        self.tree_changes.clear()

        try:
            with busy_cursor():
                table_diffs = list(
                    GeoVCSConnectionManager().get_diffs(commit)
                )
        except Exception as exception:  # noqa: BLE001 - keep the dialog usable
            QgsMessageLog.logMessage(
                f"Unable to load changes for commit '{commit}': {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            return

        for table_diff in table_diffs:
            table_node = QTreeWidgetItem(self.tree_changes)
            table_node.setText(0, table_diff.table_name)

            for feature_delta in table_diff.feature_deltas:
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
                    f"{action_icon} {safe_text(feature_delta.objectid)}: "
                    f"{feature_delta.action.name}",
                )

                for attribute_delta in feature_delta.attribute_deltas:
                    attribute_node = QTreeWidgetItem(feature_node)
                    attribute_node.setText(0, attribute_delta.name)
                    attribute_node.setText(1, safe_text(attribute_delta.from_value))
                    attribute_node.setText(2, safe_text(attribute_delta.to_value))

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
