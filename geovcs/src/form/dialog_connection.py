import os

from qgis.core import Qgis, QgsMessageLog
from qgis.gui import QgsAuthSettingsWidget
from qgis.PyQt import uic
from qgis.PyQt.QtGui import QIntValidator
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnection, GeoVCSConnectionManager

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_connection.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogConnection(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.auth_settings = QgsAuthSettingsWidget(self)
        self.v_box_layout.addWidget(self.auth_settings)

        validator_port = QIntValidator(0, 9999)
        self.edit_port.setValidator(validator_port)

        self.dialog_button_box.accepted.connect(self._accept)
        self.dialog_button_box.rejected.connect(self.reject)

        self.button_test.clicked.connect(self._test)

    def _validate(self) -> bool:
        if not self.edit_host.text().strip():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Host address is required.",
            )
            self.edit_host.setFocus()
            return False

        if not self.edit_port.text().strip():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Port number is required.",
            )
            self.edit_port.setFocus()
            return False

        if not self.edit_database.text().strip():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Database name is required.",
            )
            self.edit_database.setFocus()
            return False

        if not self.edit_branch.text().strip():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Branch name is required.",
            )
            self.edit_branch.setFocus()
            return False

        if not self.auth_settings.configId():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Credentials are required.",
            )
            return False

        connection = self._get_data()
        try:
            result = connection.test()
            if not result:
                QMessageBox.critical(
                    self,
                    "Connection Error",
                    "Check your credentials and server availability.",
                )
                return False
        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Check your credentials and server availability: {e}.",
            )
            return False
        return True

    def _test(self):
        self.setEnabled(False)
        if self._validate():
            iface.messageBar().pushMessage(  # type: ignore
                "GeoVCS - Connection Established",
                f"Connection with database instance '{self.edit_host}:{self.edit_port}@{self.edit_database}/{self.edit_branch}' established successfully.",
                Qgis.MessageLevel.Success,
            )
        self.setEnabled(True)

    def _accept(self):
        self.setEnabled(False)
        if self._validate():
            self.accept()
        self.setEnabled(True)

    def _get_data(self) -> GeoVCSConnection:
        return GeoVCSConnection(
            host=self.edit_host.text().strip(),
            port=self.edit_port.text().strip(),
            database=self.edit_database.text().strip(),
            branch=self.edit_branch.text().strip(),
            auth_config_id=self.auth_settings.configId(),
        )

    def _load_data_from_connection_manager(self):
        self.edit_host.setText(GeoVCSConnectionManager().host)
        self.edit_port.setText(GeoVCSConnectionManager().port)
        self.edit_database.setText(GeoVCSConnectionManager().database)
        self.edit_branch.setText(GeoVCSConnectionManager().branch)
        self.auth_settings.setConfigId(GeoVCSConnectionManager().get_auth_config_id)

    @classmethod
    def execute(cls, parent=None) -> tuple[GeoVCSConnection | None, bool]:
        dialog = cls(parent)

        if GeoVCSConnectionManager().is_connected:
            dialog._load_data_from_connection_manager()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._get_data(), True
        return None, False


class GeoVCSDialogConnectionCreate(GeoVCSDialogConnection):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GeoVCS - Create Connection")
        self.edit_branch.setText("main")


class GeoVCSDialogConnectionEdit(GeoVCSDialogConnection):
    def __init__(self, data: GeoVCSConnection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GeoVCS - Edit Connection")
