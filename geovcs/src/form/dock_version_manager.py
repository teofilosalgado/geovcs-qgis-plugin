import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDockWidget

from geovcs.src.constant import FORM_DIRECTORY_PATH

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dock_version_manager.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDockVersionManagerDock(QDockWidget, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
