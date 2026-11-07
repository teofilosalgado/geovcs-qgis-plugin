import os
import re
from re import Match

from qgis.core import Qgis, QgsApplication, QgsMapLayer, QgsMessageLog, QgsProject
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDialog, QDockWidget, QMessageBox
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH, regex
from geovcs.src.form import GeoVCSDialogCreateBranch, GeoVCSDialogMergeBranch
from geovcs.src.model import GeoVCSConnectionManager
from geovcs.src.util import busy_cursor

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dock_version_manager.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDockVersionManagerDock(QDockWidget, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.button_create_branch.setIcon(
            QgsApplication.getThemeIcon("/mActionAdd.svg")
        )

        self.button_refresh_branches.setIcon(
            QgsApplication.getThemeIcon("/mActionRefresh.svg")
        )
        self.button_merge_branch.setIcon(
            QgsApplication.getThemeIcon("/mIconConnect.svg")
        )

        self.button_refresh_changes.setIcon(
            QgsApplication.getThemeIcon("/mActionRefresh.svg")
        )

        self.model_status = QStandardItemModel()
        self.model_status.setHorizontalHeaderLabels(["Status", "Object"])

        self.table_status.setModel(self.model_status)
        self.table_status.horizontalHeader().setStretchLastSection(True)

        self.button_create_branch.clicked.connect(self.create_branch)
        self.button_commit.clicked.connect(self.commit)
        self.button_refresh_changes.clicked.connect(self.refresh_changes)
        self.button_refresh_branches.clicked.connect(self.refresh_branches)
        self.button_merge_branch.clicked.connect(self.merge_branch)

        # The .ui file ships disabled so that the panel cannot be used before
        # the connection manager is ready. Enable the shell here and let each
        # action degrade gracefully when there is no active connection.
        self.setEnabled(True)
        self._update_connection_state()

        QgsProject.instance().layersAdded.connect(self.on_layers_added)
        iface.projectRead.connect(self.on_project_read)

        if GeoVCSConnectionManager().is_connected:
            self._update_branches()
            self._update_changes()

    def _report_error(self, title: str, exception: Exception):
        message = f"{type(exception).__name__}: {exception}"
        QgsMessageLog.logMessage(message, "GeoVCS", Qgis.MessageLevel.Critical)
        self._notify(title, message, Qgis.MessageLevel.Critical, 10)

    @staticmethod
    def _notify(title: str, message: str, level, duration: int = 5):
        try:
            iface.messageBar().pushMessage(title, message, level, duration)
        except Exception:  # noqa: BLE001 - notifications are best effort
            pass

    def _update_connection_state(self):
        connected = GeoVCSConnectionManager().is_connected
        manager = GeoVCSConnectionManager()
        self.edit_connection.setText(
            f"{manager.database}@{manager.host}" if connected else ""
        )
        for widget in (
            self.combo_branches,
            self.button_create_branch,
            self.button_merge_branch,
            self.button_commit,
            self.edit_message,
        ):
            widget.setEnabled(connected)

        # Keep the refresh buttons available even while disconnected so the
        # user can recover as soon as the database is reachable again.
        self.button_refresh_branches.setEnabled(True)
        self.button_refresh_changes.setEnabled(True)

        if not connected:
            self.combo_branches.clear()
            self.model_status.removeRows(0, self.model_status.rowCount())

    def on_layers_added(self, layers: list[QgsMapLayer]):
        if not GeoVCSConnectionManager().is_connected:
            return

        try:
            self._configure_layers(layers)
        except Exception as exception:  # noqa: BLE001 - never break layer loading
            self._report_error("GeoVCS - Unable to configure layers", exception)

    def on_project_read(self):
        if not GeoVCSConnectionManager().is_connected:
            self._update_connection_state()
            return

        self._update_branches()
        self._update_changes()

    def create_branch(self):
        if not GeoVCSConnectionManager().is_connected:
            self._show_disconnected()
            return

        current_branch = self.combo_branches.currentText().strip()
        if not current_branch:
            QMessageBox.warning(
                self,
                "GeoVCS - Create Branch",
                "The current branch is not defined. Refresh the branch list and try again.",
            )
            return

        new_branch, ok = GeoVCSDialogCreateBranch.execute(current_branch, self)
        if not ok or not new_branch:
            return

        final_branch = f"{current_branch}]{new_branch}"
        try:
            with busy_cursor():
                GeoVCSConnectionManager().create_branch(final_branch)
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            self._report_error("GeoVCS - Branch Creation Failed", exception)
            QMessageBox.critical(
                self,
                "GeoVCS - Branch Creation Failed",
                f"Could not create branch '{final_branch}':\n\n{exception}",
            )
            return

        self._notify(
            "GeoVCS - Branch Created",
            f"Branch '{final_branch}' created successfully.",
            Qgis.MessageLevel.Success,
        )
        self.change_branch(final_branch)

    def change_branch(self, branch: str):
        if not GeoVCSConnectionManager().is_connected:
            self._show_disconnected()
            return

        branch = (branch or "").strip()
        if not branch:
            return

        manager = GeoVCSConnectionManager()
        try:
            with busy_cursor():
                manager.checkout(branch)
                self._configure_layers(QgsProject.instance().mapLayers().values())
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            self._report_error(
                "GeoVCS - Unable to Switch Branch", exception
            )
            QMessageBox.critical(
                self,
                "GeoVCS - Unable to Switch Branch",
                f"Could not switch to branch '{branch}':\n\n{exception}",
            )
            # Keep the combo box in sync with the branch that is actually
            # active instead of leaving a misleading selection behind.
            self._select_current_branch()
            return

        self._notify(
            "GeoVCS - Switched Branch",
            f"Switched to branch '{branch}' successfully.",
            Qgis.MessageLevel.Success,
        )

        self._update_branches()
        self._update_changes()

    def merge_branch(self):
        if not GeoVCSConnectionManager().is_connected:
            self._show_disconnected()
            return

        dialog = GeoVCSDialogMergeBranch(self)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        finally:
            dialog.deleteLater()

        self._update_branches()
        self._update_changes()

        # The merge changes the current branch working set without changing the
        # layer datasource URI. refreshAllLayers() reloads every layer from its
        # data source, clears the render cache and repaints the canvas.
        try:
            canvas = iface.mapCanvas()
            if canvas is not None:
                canvas.refreshAllLayers()
        except Exception as exception:  # noqa: BLE001 - never break the dock
            QgsMessageLog.logMessage(
                f"Unable to refresh the map canvas after merge: {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Warning,
            )

    def refresh_changes(self):
        if not GeoVCSConnectionManager().is_connected:
            self._show_disconnected()
            return

        self._update_changes()

    def refresh_branches(self):
        if not GeoVCSConnectionManager().is_connected:
            self._show_disconnected()
            return

        self._update_branches()
        self._update_changes()

    def _show_disconnected(self):
        self._update_connection_state()
        self._notify(
            "GeoVCS - Not Connected",
            "Connect to a GeoVCS database before using the Version Manager.",
            Qgis.MessageLevel.Warning,
        )

    def commit(self):
        if not GeoVCSConnectionManager().is_connected:
            self._show_disconnected()
            return

        message = self.edit_message.toPlainText().strip()
        if not message:
            QMessageBox.warning(
                self,
                "GeoVCS - Commit",
                "A commit message is required.",
            )
            self.edit_message.setFocus()
            return

        manager = GeoVCSConnectionManager()
        try:
            with busy_cursor():
                changes = list(manager.get_changes())
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            self._report_error("GeoVCS - Commit Failed", exception)
            QMessageBox.critical(
                self,
                "GeoVCS - Commit Failed",
                f"Could not read pending changes:\n\n{exception}",
            )
            return

        if not changes:
            QMessageBox.information(
                self,
                "GeoVCS - Commit",
                "There are no changes to commit on the current branch.",
            )
            return

        self.edit_message.setEnabled(False)
        self.button_commit.setEnabled(False)
        try:
            with busy_cursor():
                hash = manager.add_all_and_commit(message)
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            self._report_error("GeoVCS - Commit Failed", exception)
            QMessageBox.critical(
                self,
                "GeoVCS - Commit Failed",
                f"Could not create the commit:\n\n{exception}",
            )
            return
        finally:
            self.edit_message.setEnabled(True)
            self.button_commit.setEnabled(True)

        self._notify(
            "GeoVCS - Commit Created",
            f"Commit '{hash}' created successfully.",
            Qgis.MessageLevel.Success,
        )
        self.edit_message.clear()
        self._update_changes()

    def _configure_layers(self, layers):
        manager = GeoVCSConnectionManager()
        if not manager.is_connected or not manager.branch:
            return

        geovcs_layers: list[tuple[QgsMapLayer, Match[str]]] = []
        for geovcs_layer in layers:
            match = self._parse_geovcs_layer(geovcs_layer)
            if match:
                geovcs_layers.append((geovcs_layer, match))

        if not geovcs_layers:
            return

        for geovcs_layer, match in geovcs_layers:
            # Connect trigger after commit
            try:
                geovcs_layer.afterCommitChanges.disconnect(self._update_changes)
            except TypeError:
                pass

            geovcs_layer.afterCommitChanges.connect(self._update_changes)
            QgsMessageLog.logMessage(
                f"Layer '{geovcs_layer.name()}' trigger 'afterCommitChanges' "
                f"connected to 'self._update_changes' method",
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )

            # Update data source
            geovcs_layer_branch = match.group("branch")
            if geovcs_layer_branch and manager.branch != geovcs_layer_branch:
                new_data_source = re.sub(
                    regex.DATA_SOURCE,
                    lambda _: (
                        f"{match.group('before')}{manager.branch}{match.group('after')}"
                    ),
                    geovcs_layer.source(),
                    count=1,
                )
                if new_data_source != geovcs_layer.source():
                    QgsMessageLog.logMessage(
                        f"Updated layer '{geovcs_layer.name()}' datasource from "
                        f"'{geovcs_layer.source()}' to '{new_data_source}'",
                        "GeoVCS",
                        Qgis.MessageLevel.Success,
                    )
                    if not geovcs_layer.setDataSource(
                        new_data_source, geovcs_layer.name(), "ogr"
                    ):
                        QgsMessageLog.logMessage(
                            f"QGIS rejected the new datasource for layer "
                            f"'{geovcs_layer.name()}'",
                            "GeoVCS",
                            Qgis.MessageLevel.Warning,
                        )

        self._update_branches()
        self._update_changes()

    def _update_changes(self):
        manager = GeoVCSConnectionManager()
        if not manager.is_connected:
            self._update_connection_state()
            return

        try:
            with busy_cursor():
                changes = list(manager.get_changes())
        except Exception as exception:  # noqa: BLE001 - keep the dock usable
            self._report_error(
                "GeoVCS - Unable to Load Changes", exception
            )
            return

        self.model_status.removeRows(0, self.model_status.rowCount())
        for change in changes:
            status_item = QStandardItem(change.status or "")
            status_item.setEditable(False)

            table_item = QStandardItem(change.table_name or "")
            table_item.setEditable(False)

            self.model_status.appendRow([status_item, table_item])

        self.table_status.setModel(self.model_status)

    def _select_current_branch(self):
        manager = GeoVCSConnectionManager()
        current_branch = manager.branch
        self.combo_branches.blockSignals(True)
        try:
            index = self.combo_branches.findText(current_branch or "")
            if index >= 0:
                self.combo_branches.setCurrentIndex(index)
            elif self.combo_branches.count() > 0:
                self.combo_branches.setCurrentIndex(0)
        finally:
            self.combo_branches.blockSignals(False)

    def _update_branches(self):
        manager = GeoVCSConnectionManager()
        if not manager.is_connected:
            self._update_connection_state()
            return

        try:
            with busy_cursor():
                branches = sorted(
                    manager.get_branches(),
                    key=lambda item: item.name or "",
                )
        except Exception as exception:  # noqa: BLE001 - keep the dock usable
            self._report_error(
                "GeoVCS - Unable to Load Branches", exception
            )
            self._update_connection_state()
            return

        self.edit_connection.setText(f"{manager.database}@{manager.host}")

        self.combo_branches.blockSignals(True)
        try:
            self.combo_branches.clear()
            bold_font = QFont()
            bold_font.setBold(True)
            for branch in branches:
                self.combo_branches.addItem(branch.name)
                if manager.branch == branch.name:
                    index = self.combo_branches.count() - 1
                    self.combo_branches.setCurrentIndex(index)
                    self.combo_branches.setItemData(
                        index, bold_font, Qt.ItemDataRole.FontRole
                    )
        finally:
            self.combo_branches.blockSignals(False)

        try:
            self.combo_branches.currentTextChanged.disconnect(self.change_branch)
        except TypeError:
            pass
        self.combo_branches.currentTextChanged.connect(self.change_branch)
        self.combo_branches.setEnabled(bool(branches))
        QgsMessageLog.logMessage(
            f"Updated branches from '{manager.database}@{manager.host}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

    def _parse_geovcs_layer(self, layer: QgsMapLayer) -> re.Match[str] | None:
        source = layer.source()
        if not source:
            return None
        return re.search(regex.DATA_SOURCE, source)
