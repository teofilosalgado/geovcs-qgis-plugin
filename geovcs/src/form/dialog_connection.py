import os

from osgeo import ogr
from qgis.core import Qgis, QgsMessageLog
from qgis.gui import QgsAuthSettingsWidget
from qgis.PyQt import uic
from qgis.PyQt.QtGui import QIntValidator
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.utils import iface

from geovcs.src.constant import FORM_DIRECTORY_PATH, SETTINGS_CONNECTION_KEY
from geovcs.src.model import GeoVCSConnection, GeoVCSSettings

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_connection.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogConnection(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        QgsMessageLog.logMessage(
            f"Created form '{self.windowTitle()}' using '{FORM_FILE}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

        self.auth_settings = QgsAuthSettingsWidget(self)
        self.v_box_layout.addWidget(self.auth_settings)

        validator_port = QIntValidator(0, 9999)
        self.edit_port.setValidator(validator_port)

        self.dialog_button_box.accepted.connect(self.accept)
        self.dialog_button_box.rejected.connect(self.reject)

        self.button_test.clicked.connect(self.test)

    def _validate(self):
        if not self.edit_host.text().strip():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Host address is required.",
            )
            self.edit_host.setFocus()
            return

        if not self.edit_port.text().strip():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Port number is required.",
            )
            self.edit_port.setFocus()
            return

        if not self.edit_database.text().strip():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Database name is required.",
            )
            self.edit_database.setFocus()
            return

        if not self.auth_settings.configId():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Credentials are required.",
            )
            return

        data = self.get_data()
        try:
            datasource = ogr.Open(data.ogr_connection_string)
            if datasource is None:
                QMessageBox.critical(
                    self,
                    "Connection Error",
                    "Check your credentials and server availability.",
                )
                return
        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Check your credentials and server availability: {e}.",
            )
            return

        datasource = None
        return data

    def test(self):
        self.setEnabled(False)
        data = self._validate()
        self.setEnabled(True)

        if data:
            iface.messageBar().pushMessage(
                "GeoVCS - Connection Established",
                f"Database connection with instance '{data.host}:{data.port}' established successfully.",
                Qgis.MessageLevel.Success,
            )

    def accept(self):
        self.setEnabled(False)
        data = self._validate()
        self.setEnabled(True)

        if data:
            if GeoVCSSettings.key_exists(SETTINGS_CONNECTION_KEY):
                GeoVCSSettings.write_object(SETTINGS_CONNECTION_KEY, data)
                iface.messageBar().pushMessage(
                    "GeoVCS - Connection Updated",
                    f"Database connection '{data.connection_string}' updated successfully.",
                    Qgis.MessageLevel.Success,
                )
            else:
                GeoVCSSettings.write_object(SETTINGS_CONNECTION_KEY, data)
                iface.messageBar().pushMessage(
                    "GeoVCS - Connection Created",
                    f"Database connection '{data.connection_string}' created successfully.",
                    Qgis.MessageLevel.Success,
                )
            return super().accept()

    def get_data(self) -> GeoVCSConnection:
        return GeoVCSConnection(
            host=self.edit_host.text().strip(),
            port=self.edit_port.text().strip(),
            database=self.edit_database.text().strip(),
            auth_config_id=self.auth_settings.configId(),
            branch="main",
        )

    def set_data(self, data: GeoVCSConnection):
        self.edit_host.setText(data.host)
        self.edit_port.setText(str(data.port))
        self.edit_database.setText(data.database)
        self.auth_settings.setConfigId(data.auth_config_id)


class GeoVCSDialogConnectionCreate(GeoVCSDialogConnection):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GeoVCS - Create Connection")


class GeoVCSDialogConnectionEdit(GeoVCSDialogConnection):
    def __init__(self, data: GeoVCSConnection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GeoVCS - Edit Connection")
        self.set_data(data)
