import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

from geovcs.src.constant import FORM_DIRECTORY_PATH

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_create_branch.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogCreateBranch(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

    @classmethod
    def execute(cls, parent_branch: str, parent=None) -> tuple[str | None, bool]:
        dialog = cls(parent)
        dialog._load_data(parent_branch)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._get_data(), True
        return None, False

    def _get_data(self) -> str:
        return self.edit_new_branch.text().strip()

    def _load_data(self, parent_branch: str):
        self.edit_parent_branch.setText(parent_branch)
