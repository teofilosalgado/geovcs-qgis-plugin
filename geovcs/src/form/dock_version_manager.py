import os

from qgis.core import Qgis, QgsApplication, QgsProject
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDockWidget
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnectionManager

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dock_version_manager.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDockVersionManagerDock(QDockWidget, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.setEnabled(False)

        connection = GeoVCSConnectionManager().get_connection()
        if not connection:
            return

        self.edit_connection.setText(f"{connection.database}@{connection.host}")

        self.edit_branch.insertItem(0, connection.branch)
        self.edit_branch.setItemData(0, QFont().setBold(True), Qt.ItemDataRole.FontRole)
        branches = GeoVCSConnectionManager().get_branches()
        for index, branch in enumerate(branches):
            if branch != connection.branch:
                self.edit_branch.insertItem(index + 1, branch)
        self.edit_branch.setCurrentIndex(0)

        self.button_create_branch.setIcon(
            QgsApplication.getThemeIcon("/mActionAdd.svg")
        )

        self.model_status = QStandardItemModel()
        self.model_status.setHorizontalHeaderLabels(["Status", "Object"])

        self.table_status.setModel(self.model_status)
        self.table_status.horizontalHeader().setStretchLastSection(True)

        self.button_commit.clicked.connect(self.commit)

        iface.projectRead.connect(self.on_project_read)

    def on_project_read(self):
        QgsProject.instance().layersAdded.connect(self.udpate_status_on_layer_change)
        self.udpate_status_on_layer_change(QgsProject.instance().mapLayers().values())

        self.update_status()
        self.setEnabled(True)

    def udpate_status_on_layer_change(self, layers):
        for layer in layers:
            if layer.providerType() == "ogr" and layer.source().startswith("MySQL:"):
                try:
                    layer.afterCommitChanges.disconnect(self.update_status)
                except TypeError:
                    pass
                layer.afterCommitChanges.connect(self.update_status)

    def update_status(self):
        self.model_status.removeRows(0, self.model_status.rowCount())
        for change in GeoVCSConnectionManager().get_changes():
            status_item = QStandardItem(change.status)
            status_item.setEditable(False)

            table_item = QStandardItem(change.table)
            table_item.setEditable(False)

            self.model_status.appendRow([status_item, table_item])

    def commit(self):
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
            self.update_status()
        self.setEnabled(True)
