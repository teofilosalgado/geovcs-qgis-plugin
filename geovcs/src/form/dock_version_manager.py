import os
import re

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH, regex
from geovcs.src.model import GeoVCSConnectionManager

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dock_version_manager.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDockVersionManagerDock(QDockWidget, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.setEnabled(False)
        self._update_branches()

        self.button_create_branch.setIcon(
            QgsApplication.getThemeIcon("/mActionAdd.svg")
        )
        self.button_refresh.setIcon(QgsApplication.getThemeIcon("/mActionRefresh.svg"))

        self.model_status = QStandardItemModel()
        self.model_status.setHorizontalHeaderLabels(["Status", "Object"])

        self.table_status.setModel(self.model_status)
        self.table_status.horizontalHeader().setStretchLastSection(True)

        self.button_commit.clicked.connect(self.commit)
        self.button_refresh.clicked.connect(self.refresh)

        self.combo_branch.currentTextChanged.connect(self.on_branch_changed)

        QgsProject.instance().layersAdded.connect(self.on_layers_added)
        iface.projectRead.connect(self.on_project_read)

        self.setEnabled(True)

    def on_branch_changed(self, branch):

        self._update_layers_data_sources()

    def on_layers_added(self, layers):
        self._update_status_on_layer_change(layers)
        self._update_status()

    def on_project_read(self):
        self._update_layers_data_sources()
        self._update_status()

    def refresh(self):
        self._update_status()

    def _update_status_on_layer_change(self, layers):
        for layer in layers:
            if layer.providerType() == "ogr" and layer.source().startswith("MySQL:"):
                try:
                    layer.afterCommitChanges.disconnect(self._update_status)
                except TypeError:
                    pass
                layer.afterCommitChanges.connect(self._update_status)

    def _update_layers_data_sources(self):
        if not GeoVCSConnectionManager().is_connected:
            return

        geovcs_layers = [
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if layer.providerType() == "ogr" and layer.source().startswith("MySQL:")
        ]

        for geovcs_layer in geovcs_layers:
            match = re.search(regex.DATA_SOURCE, geovcs_layer.source())
            if match:
                geovcs_layer_branch = match.group("branch")
                if (
                    geovcs_layer_branch
                    and GeoVCSConnectionManager().get_current_branch()
                    != geovcs_layer_branch
                ):
                    new_data_source = re.sub(
                        regex.DATA_SOURCE,
                        rf"\g<before>{GeoVCSConnectionManager().get_current_branch()}\g<after>",
                        geovcs_layer.source(),
                    )
                    geovcs_layer.setDataSource(
                        new_data_source, geovcs_layer.name(), "ogr"
                    )
                    QgsMessageLog.logMessage(
                        f"Changed layer '{geovcs_layer.name()}' datasource from '{geovcs_layer.source()}' to '{new_data_source}'"
                        "GeoVCS",
                        Qgis.MessageLevel.Success,
                    )

    def _update_status(self):
        if not GeoVCSConnectionManager().is_connected:
            return

        has_geovcs_layers = any(
            layer.providerType() == "ogr" and layer.source().startswith("MySQL:")
            for layer in QgsProject.instance().mapLayers().values()
        )

        if has_geovcs_layers:
            self.model_status.removeRows(0, self.model_status.rowCount())
            for change in GeoVCSConnectionManager().get_changes():
                status_item = QStandardItem(change.status)
                status_item.setEditable(False)

                table_item = QStandardItem(change.table)
                table_item.setEditable(False)

                self.model_status.appendRow([status_item, table_item])

    def _update_branches(self):
        self.combo_branch.clear()

        if not GeoVCSConnectionManager().is_connected:
            return

        self.edit_connection.setText(
            f"{GeoVCSConnectionManager().database}@{GeoVCSConnectionManager().host}"
        )
        self.combo_branch.insertItem(0, GeoVCSConnectionManager().branch)
        self.combo_branch.setItemData(
            0, QFont().setBold(True), Qt.ItemDataRole.FontRole
        )

        branches = sorted(
            GeoVCSConnectionManager().get_branches(),
            key=lambda item: (item != "main", item),
        )
        for index, branch in enumerate(branches):
            if branch != GeoVCSConnectionManager().branch:
                self.combo_branch.insertItem(index + 1, branch)
        self.combo_branch.setCurrentIndex(0)

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
            self._update_status()
        self.edit_message.clear()
        self.setEnabled(True)
