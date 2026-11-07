import os

from qgis.gui import QgsAuthSettingsWidget
from qgis.PyQt import uic
from qgis.PyQt.QtGui import QIntValidator
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QMessageBox

from geovcs.src.constant import FORM_DIRECTORY_PATH
from geovcs.src.model import GeoVCSConnection, GeoVCSConnectionManager
from geovcs.src.util import busy_cursor

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_connection.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogConnection(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.auth_settings = QgsAuthSettingsWidget(self)
        self.v_box_layout.addWidget(self.auth_settings)

        self.edit_port.setValidator(QIntValidator(1, 65535, self))

        self.dialog_button_box.accepted.connect(self._accept)
        self.dialog_button_box.rejected.connect(self.reject)

        self.button_test.clicked.connect(self._test)

    def _warn(self, message: str, widget=None):
        QMessageBox.warning(
            self,
            f"{self.windowTitle()} - Validation Error",
            message,
        )
        if widget is not None:
            widget.setFocus()

    def _validate(self, notify_success: bool = False) -> bool:
        host = self.edit_host.text().strip()
        port = self.edit_port.text().strip()
        database = self.edit_database.text().strip()
        branch = self.edit_branch.text().strip()

        if not host:
            self._warn("Host address is required.", self.edit_host)
            return False

        if not port:
            self._warn("Port number is required.", self.edit_port)
            return False

        try:
            port_number = int(port)
        except ValueError:
            self._warn("Port number must be a valid integer.", self.edit_port)
            return False

        if not 1 <= port_number <= 65535:
            self._warn("Port number must be between 1 and 65535.", self.edit_port)
            return False

        if not database:
            self._warn("Database name is required.", self.edit_database)
            return False

        if not branch:
            self._warn("Branch name is required.", self.edit_branch)
            return False

        if not self.auth_settings.configId():
            self._warn("An authentication configuration is required.")
            return False

        connection = self._get_data()
        if not connection.username or not connection.password:
            self._warn(
                "The selected authentication configuration does not contain a username and password."
            )
            return False

        try:
            with busy_cursor():
                result = connection.test()
        except Exception as exception:  # noqa: BLE001 - shown to the user
            QMessageBox.critical(
                self,
                "Connection Exception",
                f"Exception while connecting to server: {type(exception).__name__}: {exception}\n\n"
                "Hint: check if the database is available and the credentials are valid.",
            )
            return False

        if result.status:
            if notify_success:
                QMessageBox.information(
                    self,
                    "Connection Established",
                    f"Connection with database instance '{host}:{port}@{database}/{branch}' "
                    f"established successfully.\n\nDolt Version: {result.dolt_version}\n"
                    f"MySQL Version: {result.mysql_version}",
                )
            return True

        QMessageBox.critical(
            self,
            "Connection Error",
            result.message
            or "Check your credentials and server availability.",
        )
        return False

    def _set_busy(self, busy: bool):
        # Do not disable the whole dialog: the validation message boxes are
        # children of this dialog and would become unresponsive too. Keep the
        # Cancel button active so the user can always abandon a slow test.
        self.button_test.setEnabled(not busy)
        ok_button = self.dialog_button_box.button(
            QDialogButtonBox.StandardButton.Ok
        )
        if ok_button is not None:
            ok_button.setEnabled(not busy)

    def _test(self):
        self._set_busy(True)
        try:
            self._validate(notify_success=True)
        finally:
            self._set_busy(False)

    def _accept(self):
        self._set_busy(True)
        try:
            if self._validate():
                self.accept()
        finally:
            self._set_busy(False)

    def _get_data(self) -> GeoVCSConnection:
        return GeoVCSConnection(
            host=self.edit_host.text().strip(),
            port=self.edit_port.text().strip(),
            database=self.edit_database.text().strip(),
            branch=self.edit_branch.text().strip(),
            auth_config_id=self.auth_settings.configId(),
        )

    def _load_data_from_connection_manager(self):
        manager = GeoVCSConnectionManager()
        self.edit_host.setText(manager.host or "")
        self.edit_port.setText(manager.port or "")
        self.edit_database.setText(manager.database or "")
        self.edit_branch.setText(manager.branch or "")
        if manager.auth_config_id:
            self.auth_settings.setConfigId(manager.auth_config_id)

    def _load_data(self, data: GeoVCSConnection):
        self.edit_host.setText(data.host or "")
        self.edit_port.setText(data.port or "")
        self.edit_database.setText(data.database or "")
        self.edit_branch.setText(data.branch or "")
        if data.auth_config_id:
            self.auth_settings.setConfigId(data.auth_config_id)

    @classmethod
    def execute(cls, parent=None) -> tuple[GeoVCSConnection | None, bool]:
        dialog = cls(parent)

        if GeoVCSConnectionManager().is_connected:
            dialog._load_data_from_connection_manager()

        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                return dialog._get_data(), True
            return None, False
        finally:
            dialog.deleteLater()


class GeoVCSDialogConnectionCreate(GeoVCSDialogConnection):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GeoVCS - Create Connection")
        self.edit_branch.setText("main")


class GeoVCSDialogConnectionEdit(GeoVCSDialogConnection):
    def __init__(self, data: GeoVCSConnection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GeoVCS - Edit Connection")
        self._load_data(data)

    @classmethod
    def execute_for(
        cls, data: GeoVCSConnection, parent=None
    ) -> tuple[GeoVCSConnection | None, bool]:
        dialog = cls(data, parent)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                return dialog._get_data(), True
            return None, False
        finally:
            dialog.deleteLater()
