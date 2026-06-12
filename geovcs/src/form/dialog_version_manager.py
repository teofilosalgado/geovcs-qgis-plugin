import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnection

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_version_manager.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogVersionManager(QDialog, FORM_CLASS):
    def __init__(self, data: GeoVCSConnection, parent=None):
        super().__init__(parent)
        self.setupUi(self)
