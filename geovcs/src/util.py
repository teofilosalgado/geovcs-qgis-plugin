import os
from functools import cache

from qgis.PyQt.QtGui import QIcon


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
