import os
import re

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH, regex
from geovcs.src.form import GeoVCSDialogCreateBranch
from geovcs.src.model import GeoVCSConnectionManager

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dock_version_manager.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDockVersionManagerDock(QDockWidget, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.button_create_branch.setIcon(
            QgsApplication.getThemeIcon("/mActionAdd.svg")
        )
        self.button_refresh_changes.setIcon(
            QgsApplication.getThemeIcon("/mActionRefresh.svg")
        )
        self.button_refresh_branches.setIcon(
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

        if GeoVCSConnectionManager().is_connected:
            self.edit_connection.setText(
                f"{GeoVCSConnectionManager().database}@{GeoVCSConnectionManager().host}"
            )

        QgsProject.instance().layersAdded.connect(self.on_layers_added)
        iface.projectRead.connect(self.on_project_read)

    def change_branch(self, branch):
        if not branch:
            return

        GeoVCSConnectionManager().checkout(branch)
        iface.messageBar().pushMessage(  # type: ignore
            "GeoVCS - Switched Branch",
            f"Switched to branch '{branch}' successfully.",
            Qgis.MessageLevel.Success,
        )

        self._configure_layers(QgsProject.instance().mapLayers().values())
        self._update_branches()
        self._update_changes()

    def on_layers_added(self, layers):
        QgsMessageLog.logMessage(
            f"Added '{len(layers)}' layer(s) to current project",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
        self._configure_layers(layers)
        self._update_branches()
        self._update_changes()

    def on_project_read(self):
        QgsMessageLog.logMessage(
            "Project is ready",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
        self._update_branches()
        self._update_changes()

    def create_branch(self):
        current_branch = self.combo_branches.currentText().strip()
        new_branch, ok = GeoVCSDialogCreateBranch().execute(current_branch)
        if not ok or not new_branch:
            return

        final_branch = f"{current_branch}]{new_branch}"
        GeoVCSConnectionManager().create_branch(final_branch)
        iface.messageBar().pushMessage(  # type: ignore
            "GeoVCS - Branch Created",
            f"Branch '{final_branch}' created successfully.",
            Qgis.MessageLevel.Success,
        )
        self.change_branch(final_branch)

    def refresh_changes(self):
        self._update_changes()

    def refresh_branches(self):
        self._update_branches()
        self._update_changes()

    def commit(self):
        if not GeoVCSConnectionManager().is_connected:
            return

        message = self.edit_message.toPlainText().strip()
        if not message:
            return

        self.setEnabled(False)
        hash = GeoVCSConnectionManager().add_all_and_commit(message)
        if hash:
            iface.messageBar().pushMessage(  # type: ignore
                "GeoVCS - Commit Created",
                f"Commit '{hash}' created successfully.",
                Qgis.MessageLevel.Success,
            )
            self._update_changes()
        self.edit_message.clear()
        self.setEnabled(True)

    def _configure_layers(self, layers):
        if not GeoVCSConnectionManager().is_connected:
            return

        for layer in layers:
            if layer.providerType() != "ogr" or not layer.source().startswith("MySQL:"):
                continue

            # Update data source
            match = re.search(regex.DATA_SOURCE, layer.source())
            if match:
                geovcs_layer_branch = match.group("branch")
                if (
                    geovcs_layer_branch
                    and GeoVCSConnectionManager().branch != geovcs_layer_branch
                ):
                    new_data_source = re.sub(
                        regex.DATA_SOURCE,
                        rf"\g<before>{GeoVCSConnectionManager().branch}\g<after>",
                        layer.source(),
                    )
                    QgsMessageLog.logMessage(
                        f"Updated layer '{layer.name()}' datasource from '{layer.source()}' to '{new_data_source}'",
                        "GeoVCS",
                        Qgis.MessageLevel.Success,
                    )
                    layer.setDataSource(new_data_source, layer.name(), "ogr")

            # Connect trigger after commit
            try:
                layer.afterCommitChanges.disconnect(self._update_changes)
            except TypeError:
                pass

            layer.afterCommitChanges.connect(self._update_changes)
            QgsMessageLog.logMessage(
                f"Layer '{layer.name()}' trigger 'afterCommitChanges' connected to 'self._update_changes' method",
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )

    def _update_changes(self):
        if not GeoVCSConnectionManager().is_connected:
            return

        has_geovcs_layers = any(
            layer.providerType() == "ogr" and layer.source().startswith("MySQL:")
            for layer in QgsProject.instance().mapLayers().values()
        )

        if has_geovcs_layers:
            self.setEnabled(True)
            self.model_status.removeRows(0, self.model_status.rowCount())
            for change in GeoVCSConnectionManager().get_changes():
                status_item = QStandardItem(change.status)
                status_item.setEditable(False)

                table_item = QStandardItem(change.table_name)
                table_item.setEditable(False)

                self.model_status.appendRow([status_item, table_item])
                QgsMessageLog.logMessage(
                    f"Received change '{change.table_name}' from '{GeoVCSConnectionManager().database}@{GeoVCSConnectionManager().host}' at '{GeoVCSConnectionManager().branch}'",
                    "GeoVCS",
                    Qgis.MessageLevel.Success,
                )
            self.table_status.setModel(self.model_status)

    def _update_branches(self):
        if not GeoVCSConnectionManager().is_connected:
            return

        self.edit_connection.setText(
            f"{GeoVCSConnectionManager().database}@{GeoVCSConnectionManager().host}"
        )

        try:
            self.combo_branches.currentTextChanged.disconnect()
        except TypeError:
            pass

        self.combo_branches.clear()
        branches = sorted(
            GeoVCSConnectionManager().get_branches(),
            key=lambda item: item.name,
        )
        for index, branch in enumerate(branches):
            self.combo_branches.insertItem(index, branch.name)
            if GeoVCSConnectionManager().branch == branch.name:
                self.combo_branches.setCurrentIndex(index)
                self.combo_branches.setItemData(
                    index, QFont().setBold(True), Qt.ItemDataRole.FontRole
                )

        self.combo_branches.currentTextChanged.connect(self.change_branch)
        QgsMessageLog.logMessage(
            f"Updated branches from '{GeoVCSConnectionManager().database}@{GeoVCSConnectionManager().host}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
