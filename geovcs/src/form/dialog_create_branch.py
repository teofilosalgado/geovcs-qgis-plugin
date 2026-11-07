import os

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QRegularExpression
from qgis.PyQt.QtGui import QRegularExpressionValidator
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from geovcs.src.constant import FORM_DIRECTORY_PATH

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_create_branch.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)

BRANCH_NAME_PATTERN = QRegularExpression("^[a-z0-9_]+$")


class GeoVCSDialogCreateBranch(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.edit_new_branch.setValidator(
            QRegularExpressionValidator(BRANCH_NAME_PATTERN, self)
        )
        self.edit_parent_branch.setText("")

    def accept(self):
        if not self._validate():
            return
        super().accept()

    def _validate(self) -> bool:
        parent_branch = self.edit_parent_branch.text().strip()
        new_branch = self.edit_new_branch.text().strip()

        if not parent_branch:
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "The parent branch is not defined. Refresh the branch list and try again.",
            )
            return False

        if not new_branch:
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "A new branch name is required.",
            )
            self.edit_new_branch.setFocus()
            return False

        if not BRANCH_NAME_PATTERN.match(new_branch).hasMatch():
            QMessageBox.warning(
                self,
                f"{self.windowTitle()} - Validation Error",
                "Branch names may only contain lowercase letters (a-z), digits (0-9) "
                "and underscores (_).",
            )
            self.edit_new_branch.setFocus()
            return False

        return True

    @classmethod
    def execute(cls, parent_branch: str, parent=None) -> tuple[str | None, bool]:
        dialog = cls(parent)
        dialog._load_data(parent_branch)

        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                return dialog._get_data(), True
            return None, False
        finally:
            dialog.deleteLater()

    def _get_data(self) -> str:
        return self.edit_new_branch.text().strip()

    def _load_data(self, parent_branch: str):
        self.edit_parent_branch.setText(parent_branch or "")
