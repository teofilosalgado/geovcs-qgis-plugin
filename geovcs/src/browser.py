import posixpath

from osgeo import ogr
from osgeo.ogr import Layer
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsConnectionsRootItem,
    QgsDataItem,
    QgsDataItemProvider,
    QgsLayerItem,
    QgsMessageLog,
)
from qgis.gui import QgsDataItemGuiProvider
from qgis.PyQt.QtWidgets import QAction, QDialog  # type: ignore
from qgis.utils import iface

from geovcs.src.constant import PROVIDER_KEY, SETTINGS_CONNECTION_KEY
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
            geovcs_layer.uri,
            geovcs_layer.layer_type,
            geovcs_layer.provider_key,
        )
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.NoCapabilities)
        self.setState(Qgis.BrowserItemState.Populated)

    def hasChildren(self):
        return False


class GeoVCSConnectionsRootItem(QgsConnectionsRootItem):
    def __init__(self, parent):
        super().__init__(parent, PROVIDER_KEY, f"/{PROVIDER_KEY}", PROVIDER_KEY)
        QgsMessageLog.logMessage(
            "__init__'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )

        self.setCapabilitiesV2(Qgis.BrowserItemCapability.Fertile)
        self.connection: GeoVCSConnection | None = None
        self._update_connection()

    def _update_connection(self):
        if GeoVCSSettings.key_exists(SETTINGS_CONNECTION_KEY):
            self.setState(Qgis.BrowserItemState.NotPopulated)
            self.connection = GeoVCSSettings.read_object(
                SETTINGS_CONNECTION_KEY,
                GeoVCSConnection,
            )
            self.setName(
                f"GeoVCS at {self.connection.database}/{self.connection.branch}"
            )
            QgsMessageLog.logMessage(
                f"Found GeoVCS connection '{self.connection.connection_string}'",
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )
        else:
            self.connection = None
            self.setName("GeoVCS")
            self.setState(Qgis.BrowserItemState.Populated)

    def icon(self):
        return get_logo()

    def hasChildren(self):
        return self.connection is not None

    def refresh(self, children: list[QgsDataItem] = []) -> None:
        return super().refresh()

    def depopulate(self) -> None:
        return super().depopulate()

    def createChildren(self) -> list[GeoVCSLayerItem]:  # type: ignore
        self._update_connection()

        if not self.connection:
            self.setState(Qgis.BrowserItemState.Populated)
            return []

        self.setState(Qgis.BrowserItemState.Populating)
        items: list[GeoVCSLayerItem] = []
        datasource = ogr.Open(self.connection.ogr_connection_string)
        QgsMessageLog.logMessage(
            f"Connected to GeoVCS '{self.connection.connection_string}'",
            "GeoVCS",
            Qgis.MessageLevel.Success,
        )
        layer_count = datasource.GetLayerCount()
        QgsMessageLog.logMessage(
            f"Found {layer_count} layers in {self.connection.connection_string}",
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
                f"Layer '{item.geovcs_layer.name}' of type '{item.geovcs_layer.layer_type.name}' loaded from '{item.geovcs_layer.uri}'",  # type: ignore
                "GeoVCS",
                Qgis.MessageLevel.Success,
            )
        datasource = None

        self.setState(Qgis.BrowserItemState.Populated)
        return items


class GeoVCSDataItemProvider(QgsDataItemProvider):
    def name(self):
        return "GeoVCS"

    def capabilities(self):  # type: ignore
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

            if not GeoVCSSettings.key_exists(SETTINGS_CONNECTION_KEY):
                return

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

    def _refresh(self, item: GeoVCSConnectionsRootItem):
        item.refresh()

    def _edit(self, item: GeoVCSConnectionsRootItem):
        if item.connection is None:
            item.refresh()
            return

        dialog_edit_connection = GeoVCSDialogConnectionEdit(item.connection)
        if dialog_edit_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()

    def _disconnect(self, item: GeoVCSConnectionsRootItem):
        if item.connection is None:
            return

        GeoVCSSettings.remove(SETTINGS_CONNECTION_KEY)
        iface.messageBar().pushMessage(  # type: ignore
            "GeoVCS - Connection Removed",
            f"Database connection '{item.connection.connection_string}' disconnected successfully.",
            Qgis.MessageLevel.Success,
        )
        item.depopulate()
        item.refresh()

    def _version_manager(self, item: GeoVCSConnectionsRootItem):
        if item.connection is None:
            item.refresh()
            return

        dialog_edit_connection = GeoVCSDialogVersionManager(item.connection)
        if dialog_edit_connection.exec() != QDialog.DialogCode.Accepted:
            return
        item.refresh()
