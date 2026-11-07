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


def refresh_geovcs_browser() -> None:
    """Refresh the GeoVCS root item and its layer tree in the QGIS Browser.

    The root item name includes the active branch and every layer URI contains
    the branch as well, so both must be rebuilt after a checkout.
    """
    try:
        from qgis.utils import iface

        from geovcs.src.constant import PROVIDER_KEY

        if iface is None:
            return

        model = iface.browserModel()
        if model is None:
            return

        root_path = f"/{PROVIDER_KEY}"
        model.refresh(root_path)
        model.refresh(f"{root_path}/layers")
    except Exception:  # noqa: BLE001 - browser synchronization is best effort
        pass


def refresh_version_manager_dock() -> None:
    """Synchronize every open Version Manager dock with the current state.

    Branch lists live in more than one place (the dock combo box, the history
    dialog and the merge dialog). Whenever a branch is created or deleted
    outside the dock, the dock must be refreshed so it does not keep offering
    a branch that no longer exists on the server.
    """
    try:
        from qgis.utils import iface

        from geovcs.src.form.dock_version_manager import (
            GeoVCSDockVersionManagerDock,
        )
        from geovcs.src.model import GeoVCSConnectionManager

        if iface is None:
            return

        main_window = iface.mainWindow()
        if main_window is None:
            return

        manager = GeoVCSConnectionManager()
        for dock in main_window.findChildren(GeoVCSDockVersionManagerDock):
            if manager.is_connected:
                dock.refresh_branches()
            else:
                dock._update_connection_state()
    except Exception:  # noqa: BLE001 - UI synchronization is best effort
        pass
