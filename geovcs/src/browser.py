import posixpath

from osgeo import ogr
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsConnectionsRootItem,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsDataItemProvider,
    QgsLayerItem,
    QgsMessageLog,
)
from qgis.gui import QgsDataItemGuiProvider
from qgis.PyQt.QtWidgets import QAction, QDialog
from qgis.utils import iface

from geovcs.src.constant import PROVIDER_KEY
from geovcs.src.form import (
    GeoVCSDialogConnectionCreate,
    GeoVCSDialogConnectionEdit,
    GeoVCSDialogVersionManager,
)
from geovcs.src.model import GeoVCSConnection, GeoVCSLayer, GeoVCSSettings
from geovcs.src.util import get_icon


class GeoVCSLayerItem(QgsLayerItem):
    def __init__(self, parent: QgsDataItem, geovcs_layer: GeoVCSLayer):
        self.geovcs_layer: GeoVCSLayer = geovcs_layer
        super().__init__(
            parent,
            geovcs_layer.name,
            geovcs_layer.path,
            geovcs_layer.uri,
            geovcs_layer.layer_type,
            geovcs_layer.provider_key,
        )
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.NoCapabilities)
        self.setState(Qgis.BrowserItemState.Populated)

    def hasChildren(self):
        return False


class GeoVCSDataCollectionItem(QgsDataCollectionItem):
    def __init__(self, parent: QgsDataItem, geovcs_connection: GeoVCSConnection):
        self.geovcs_connection: GeoVCSConnection = geovcs_connection
        super().__init__(
            parent,
            f"{self.geovcs_connection.name} ({self.geovcs_connection.branch})",
            posixpath.join(parent.path(), self.geovcs_connection.name),
            PROVIDER_KEY,
        )

    def icon(self):
        return QgsApplication.getThemeIcon("/mIconConnect.svg")

    def hasChildren(self):
        return True

    def createChildren(self):
        items: list[GeoVCSLayerItem] = []

        datasource = ogr.Open(self.geovcs_connection.connection_string)
        QgsMessageLog.logMessage(
            f"Connected to GeoVCS {self.geovcs_connection.name} using '{self.geovcs_connection.connection_string}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
        layer_count = datasource.GetLayerCount()
        QgsMessageLog.logMessage(
            f"Found {layer_count} layers in {self.geovcs_connection.name}",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

        for i in range(layer_count):
            layer = datasource.GetLayer(i)
            item = GeoVCSLayerItem(
                self,
                GeoVCSLayer(
                    layer.GetName(),
                    posixpath.join(self.path(), layer.GetName()),
                    layer.GetGeomType(),
                    self.geovcs_connection,
                ),
            )

            items.append(item)
            QgsMessageLog.logMessage(
                f"Layer '{item.geovcs_layer.name}' of type '{item.geovcs_layer.layer_type.name}' loaded from '{item.geovcs_layer.uri}'",
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )
        datasource = None

        return items


class GeoVCSConnectionsRootItem(QgsConnectionsRootItem):
    def __init__(self, parent):
        super().__init__(parent, PROVIDER_KEY, f"/{PROVIDER_KEY}", PROVIDER_KEY)

    def icon(self):
        return get_icon("logo.svg")

    def hasChildren(self):
        return True

    def createChildren(self):
        items: list[GeoVCSDataCollectionItem] = []
        for group in GeoVCSSettings.iterate_groups("connections"):
            connection = GeoVCSSettings.read_object(
                posixpath.join("connections", group), GeoVCSConnection
            )
            item = GeoVCSDataCollectionItem(self, connection)
            items.append(item)
        return items


class GeoVCSDataItemProvider(QgsDataItemProvider):
    def name(self):
        return "GeoVCS"

    def capabilities(self):
        return Qgis.DataItemProviderCapability.Databases

    def createDataItem(self, path, parentItem):
        if not parentItem:
            return GeoVCSConnectionsRootItem(parentItem)
        return None


class GeoVCSDataItemGuiProvider(QgsDataItemGuiProvider):
    def name(self):
        return "GeoVCS"

    def populateContextMenu(self, item, menu, selectedItems, context):
        if menu is None:
            return

        if isinstance(item, GeoVCSConnectionsRootItem):
            action_refresh_connection = QAction(
                QgsApplication.getThemeIcon("/mActionAdd.svg"),
                "New connection...",
                menu,
            )
            action_refresh_connection.triggered.connect(
                lambda: self._create_connection(item)
            )
            menu.addAction(action_refresh_connection)

        elif isinstance(item, GeoVCSDataCollectionItem):
            action_refresh_connection = QAction(
                QgsApplication.getThemeIcon("/mActionRefresh.svg"),
                "Refresh",
                menu,
            )
            action_refresh_connection.triggered.connect(
                lambda: self._refresh_connection(item)
            )
            menu.addAction(action_refresh_connection)

            action_edit_connection = QAction(
                QgsApplication.getThemeIcon("/mActionToggleEditing.svg"),
                "Edit",
                menu,
            )
            action_edit_connection.triggered.connect(
                lambda: self._edit_connection(item)
            )
            menu.addAction(action_edit_connection)

            action_version_manager = QAction(
                QgsApplication.getThemeIcon("/mIconQueryHistory.svg"),
                "Version Manager...",
                menu,
            )
            action_version_manager.triggered.connect(
                lambda: self._version_manager(item)
            )
            menu.addAction(action_version_manager)

            action_remove_connection = QAction(
                QgsApplication.getThemeIcon("/mActionRemove.svg"),
                "Remove",
                menu,
            )
            action_remove_connection.triggered.connect(
                lambda: self._remove_connection(item)
            )
            menu.addAction(action_remove_connection)

    def _create_connection(self, item: GeoVCSConnectionsRootItem):
        dialog_create_connection = GeoVCSDialogConnectionCreate()
        if dialog_create_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()

    def _refresh_connection(self, item: GeoVCSDataCollectionItem):
        item.refresh()

    def _edit_connection(self, item: GeoVCSDataCollectionItem):
        dialog_edit_connection = GeoVCSDialogConnectionEdit(item.geovcs_connection)
        if dialog_edit_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()

    def _version_manager(self, item: GeoVCSDataCollectionItem):
        dialog_edit_connection = GeoVCSDialogVersionManager(item.geovcs_connection)
        if dialog_edit_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()

    def _remove_connection(self, item: GeoVCSDataCollectionItem):
        GeoVCSSettings.remove(
            posixpath.join("connections", item.geovcs_connection.name)
        )
        iface.messageBar().pushMessage(
            "GeoVCS - Connection Removed",
            f"Database connection '{item.geovcs_connection.name}' removed successfully.",
            Qgis.MessageLevel.Success,
        )
        parent = item.parent()
        if parent:
            parent.refresh()
