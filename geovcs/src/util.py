import os
from collections.abc import Generator
from contextlib import contextmanager
from functools import cache
from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QApplication


@cache
def get_icon(file_name: str) -> QIcon:
    return QIcon(
        os.path.join(os.path.dirname(__file__), "..", "asset", "icon", file_name)
    )


@cache
def get_logo() -> QIcon:
    return QIcon(
        os.path.join(os.path.dirname(__file__), "..", "asset", "icon", "logo.svg")
    )


@contextmanager
def busy_cursor() -> Generator[None, Any, None]:
    """Show a wait cursor for the duration of a blocking operation."""
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


def safe_text(value: Any, length: int | None = None) -> str:
    """Render an optional database value without breaking the UI."""
    text = "" if value is None else str(value)
    return text[:length] if length is not None else text
