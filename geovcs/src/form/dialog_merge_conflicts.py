import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QListWidgetItem

from geovcs.src.constant import FORM_DIRECTORY_PATH

FORM_FILE = os.path.join(FORM_DIRECTORY_PATH, "dialog_merge_conflicts.ui")

FORM_CLASS, _ = uic.loadUiType(FORM_FILE)


class GeoVCSDialogMergeConflicts(QDialog, FORM_CLASS):
    def __init__(self, conflict_tables: list[str], parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self._selected_strategy: str | None = None

        self._load_tables(conflict_tables)

        self.button_keep_ours.clicked.connect(self._choose_keep_ours)
        self.button_keep_theirs.clicked.connect(self._choose_keep_theirs)
        self.button_abort.clicked.connect(self._abort)

    def _load_tables(self, tables: list[str]):
        self.list_conflict_tables.clear()
        for table in tables:
            item = QListWidgetItem(f"⚠️ {table}")
            self.list_conflict_tables.addItem(item)

    def _choose_keep_ours(self):
        self._selected_strategy = "--ours"
        self.accept()

    def _choose_keep_theirs(self):
        self._selected_strategy = "--theirs"
        self.accept()

    def _abort(self):
        self._selected_strategy = None
        self.reject()

    @classmethod
    def execute(cls, conflict_tables: list[str], parent=None) -> tuple[str | None, bool]:
        dialog = cls(conflict_tables, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._selected_strategy, True
        return None, False
