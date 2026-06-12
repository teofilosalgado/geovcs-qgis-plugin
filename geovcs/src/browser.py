import posixpath

from osgeo import ogr
from osgeo.ogr import Layer
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
from qgis.PyQt.QtWidgets import QAction, QDialog  # type: ignore
from qgis.utils import iface

from geovcs.src.constant import PROVIDER_KEY
from geovcs.src.form import (
    GeoVCSDialogConnectionCreate,
    GeoVCSDialogConnectionEdit,
    GeoVCSDialogVersionManager,
)
from geovcs.src.model import GeoVCSConnection, GeoVCSLayer, GeoVCSSettings
from geovcs.src.util import get_logo


class GeoVCSLayerItem(QgsLayerItem):
    def __init__(self, parent: QgsDataItem, geovcs_layer: GeoVCSLayer):
        self.geovcs_layer: GeoVCSLayer = geovcs_layer
        super().__init__(
            parent,
            geovcs_layer.name,
            geovcs_layer.path,
            geovcs_layer.uri.uri(False),
            geovcs_layer.layer_type,
            geovcs_layer.provider_key,
        )
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.NoCapabilities)
        self.setState(Qgis.BrowserItemState.Populated)

    def hasChildren(self):
        return False


class GeoVCSDataCollectionItem(QgsDataCollectionItem):
    def __init__(self, parent: QgsDataItem, geovcs_connection: GeoVCSConnection):
        self.connection: GeoVCSConnection = geovcs_connection
        super().__init__(
            parent,
            f"{self.connection.name} ({self.connection.branch})",
            posixpath.join(parent.path(), self.connection.name),
            PROVIDER_KEY,
        )

    def icon(self):
        return QgsApplication.getThemeIcon("/mIconConnect.svg")

    def hasChildren(self):
        return True

    def createChildren(self):  # type: ignore
        items: list[GeoVCSLayerItem] = []

        datasource = ogr.Open(self.connection.ogr_connection_string)
        QgsMessageLog.logMessage(
            f"Connected to GeoVCS {self.connection.name} using '{self.connection.connection_string}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
        layer_count = datasource.GetLayerCount()
        QgsMessageLog.logMessage(
            f"Found {layer_count} layers in {self.connection.name}",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

        for i in range(layer_count):
            layer: Layer = datasource.GetLayer(i)
            item = GeoVCSLayerItem(
                self,
                GeoVCSLayer(
                    self.connection,
                    posixpath.join(self.path(), layer.GetName()),
                    layer.GetName(),
                    layer.GetGeometryColumn(),
                    layer.GetFIDColumn(),
                    layer.GetGeomType(),
                ),
            )

            items.append(item)
            QgsMessageLog.logMessage(
                f"Layer '{item.geovcs_layer.name}' of type '{item.geovcs_layer.layer_type.name}' loaded from '{item.geovcs_layer.uri.uri(True)}'",
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )
        datasource = None

        return items


class GeoVCSConnectionsRootItem(QgsConnectionsRootItem):
    def __init__(self, parent):
        super().__init__(parent, PROVIDER_KEY, f"/{PROVIDER_KEY}", PROVIDER_KEY)

    def icon(self):
        return get_logo()

    def hasChildren(self):
        return True

    def createChildren(self):  # type: ignore
        items: list[GeoVCSLayerItem] = []

        datasource = ogr.Open(self.connection.ogr_connection_string)
        QgsMessageLog.logMessage(
            f"Connected to GeoVCS {self.connection.name} using '{self.connection.connection_string}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
        layer_count = datasource.GetLayerCount()
        QgsMessageLog.logMessage(
            f"Found {layer_count} layers in {self.connection.name}",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

        for i in range(layer_count):
            layer: Layer = datasource.GetLayer(i)
            item = GeoVCSLayerItem(
                self,
                GeoVCSLayer(
                    self.connection,
                    posixpath.join(self.path(), layer.GetName()),
                    layer.GetName(),
                    layer.GetGeometryColumn(),
                    layer.GetFIDColumn(),
                    layer.GetGeomType(),
                ),
            )

            items.append(item)
            QgsMessageLog.logMessage(
                f"Layer '{item.geovcs_layer.name}' of type '{item.geovcs_layer.layer_type.name}' loaded from '{item.geovcs_layer.uri.uri(True)}'",
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )
        datasource = None

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
            action_connect = QAction(
                QgsApplication.getThemeIcon("/repositoryConnected.svg"),
                "Connect...",
                menu,
            )
            action_connect.triggered.connect(lambda: self._connect(item))
            menu.addAction(action_connect)

            action_edit = QAction(
                QgsApplication.getThemeIcon("/mActionToggleEditing.svg"),
                "Edit connection...",
                menu,
            )
            action_edit.triggered.connect(lambda: self._edit(item))
            menu.addAction(action_edit)

            action_refresh = QAction(
                QgsApplication.getThemeIcon("/mActionRefresh.svg"),
                "Refresh",
                menu,
            )
            action_refresh.triggered.connect(lambda: self._refresh(item))
            menu.addAction(action_refresh)

            action_disconnect = QAction(
                QgsApplication.getThemeIcon("/mActionRemove.svg"),
                "Remove connection",
                menu,
            )
            action_disconnect.triggered.connect(lambda: self._disconnect(item))
            menu.addAction(action_disconnect)

    def _connect(self, item: GeoVCSConnectionsRootItem):
        dialog_create_connection = GeoVCSDialogConnectionCreate()
        if dialog_create_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()

    def _refresh(self, item: GeoVCSDataCollectionItem):
        item.refresh()

    def _edit(self, item: GeoVCSDataCollectionItem):
        dialog_edit_connection = GeoVCSDialogConnectionEdit(item.connection)
        if dialog_edit_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()

    def _disconnect(self, item: GeoVCSDataCollectionItem):
        GeoVCSSettings.remove(posixpath.join("connections", item.connection.name))
        iface.messageBar().pushMessage(
            "GeoVCS - Connection Removed",
            f"Database connection '{item.connection.connection_string}' disconnected successfully.",
            Qgis.MessageLevel.Success,
        )
        parent = item.parent()
        if parent:
            parent.refresh()

    def _version_manager(self, item: GeoVCSDataCollectionItem):
        dialog_edit_connection = GeoVCSDialogVersionManager(item.connection)
        if dialog_edit_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()
