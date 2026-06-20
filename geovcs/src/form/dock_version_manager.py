import os

from qgis.core import QgsApplication, QgsProject
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDockWidget

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnectionManager

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dock_version_manager.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDockVersionManagerDock(QDockWidget, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        connection = GeoVCSConnectionManager().get_connection()
        if not connection:
            self.setEnabled(False)
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
        self.model_status.setHorizontalHeaderLabels(["Modified Object", "Status"])

        self.table_status.setModel(self.model_status)
        self.table_status.horizontalHeader().setStretchLastSection(True)

        QgsProject.instance().layersAdded.connect(self.conectar_sinal_novas_camadas)

    def conectar_sinal_novas_camadas(self, layers):
        for layer in layers:
            if layer.providerType() == "ogr" and layer.source().startswith("MySQL:"):
                try:
                    layer.afterCommitChanges.disconnect(self.atualizar_painel_status)
                except TypeError:
                    pass
                layer.afterCommitChanges.connect(self.atualizar_painel_status)

    def atualizar_painel_status(self):
        self.model_status.removeRows(0, self.model_status.rowCount())
        for change in GeoVCSConnectionManager().get_changes():
            table_item = QStandardItem(change.table)
            table_item.setEditable(False)

            status_item = QStandardItem(change.status)
            status_item.setEditable(False)
            # if change.status == "modified":
            #     status_item.setForeground(Qt.darkYellow)
            # elif change.status == "added" or change.status == "new table":
            #     status_item.setForeground(Qt.darkGreen)
            # elif change.status == "deleted":
            #     status_item.setForeground(Qt.darkRed)

            # Insere a linha na QTableView
            self.model_status.appendRow([table_item, status_item])
