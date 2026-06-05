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
from geovcs.src.dialog import GeoVCSCreateConnectionDialog
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
            self.geovcs_connection.name,
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
                f"Layer '{item.geovcs_layer.name}' '{item.geovcs_layer.layer_type}' loaded from '{item.geovcs_layer.uri}'",
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
        for key in GeoVCSSettings.iterate("connections"):
            connection = GeoVCSSettings.read_object(
                posixpath.join("connections", key), GeoVCSConnection
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

        if isinstance(item, GeoVCSDataCollectionItem):
            action_refresh_connection = QAction(
                QgsApplication.getThemeIcon("/mActionRefresh.svg"),
                "Refresh",
                menu,
            )
            action_refresh_connection.triggered.connect(
                lambda: self._refresh_connection(item)
            )
            menu.addAction(action_refresh_connection)

    def _refresh_connection(self, item: GeoVCSDataCollectionItem):
        item.refresh()

    def _create_connection(self, item: QgsConnectionsRootItem):
        create_connection_dialog = GeoVCSCreateConnectionDialog()
        if create_connection_dialog.exec() != QDialog.Accepted:
            return

        iface.messageBar().pushMessage(
            "GeoVCS - Connection Created",
            f"Database connection '{create_connection_dialog.get_data().name}' stored successfully.",
            Qgis.MessageLevel.Success,
        )
        item.refresh()
