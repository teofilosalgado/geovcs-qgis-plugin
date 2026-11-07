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
    GeoVCSDialogHistory,
)
from geovcs.src.model import (
    GeoVCSConnection,
    GeoVCSConnectionManager,
    GeoVCSLayer,
)
from geovcs.src.util import get_logo, refresh_version_manager_dock


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

    def _ogr_geometry_type_to_qgis_browser_layer_type(
        self,
        ogr_geometry_type,
    ) -> Qgis.BrowserLayerType:
        if ogr_geometry_type in (
            ogr.wkbPoint,
            ogr.wkbPoint25D,
            ogr.wkbMultiPoint,
            ogr.wkbMultiPoint25D,
        ):
            return Qgis.BrowserLayerType.Point
        elif ogr_geometry_type in (
            ogr.wkbLineString,
            ogr.wkbLineString25D,
            ogr.wkbMultiLineString,
            ogr.wkbMultiLineString25D,
        ):
            return Qgis.BrowserLayerType.Line
        elif ogr_geometry_type in (
            ogr.wkbPolygon,
            ogr.wkbPolygon25D,
            ogr.wkbMultiPolygon,
            ogr.wkbMultiPolygon25D,
        ):
            return Qgis.BrowserLayerType.Polygon
        elif ogr_geometry_type == ogr.wkbNone:
            return Qgis.BrowserLayerType.Table
        else:
            return Qgis.BrowserLayerType.NoType


class GeoVCSLayerGroupItem(QgsDataCollectionItem):
    def __init__(self, parent: QgsDataItem, path: str):
        super().__init__(parent, "Layers", path, PROVIDER_KEY)
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.Fertile)
        self.setIcon(QgsApplication.getThemeIcon("/dbmanager.svg"))

    def refresh(self, children: list[QgsDataItem] | None = None) -> None:
        # A branch checkout changes every layer URI while the layer paths stay
        # the same. Drop the existing children first so the browser does not
        # reuse QgsLayerItems that still point at the previous branch.
        self.depopulate()
        return super().refresh()

    def createChildren(self) -> list[GeoVCSLayerItem]:  # type: ignore
        self.setState(Qgis.BrowserItemState.Populating)
        items: list[GeoVCSLayerItem] = []

        try:
            manager = GeoVCSConnectionManager()
            if not manager.is_connected:
                self.setState(Qgis.BrowserItemState.Populated)
                return []

            # ``get_layers`` yields plain snapshots; the underlying OGR layer
            # objects stay owned by the dataset and are never leaked here.
            for layer in manager.get_layers():
                item = GeoVCSLayerItem(
                    self,
                    GeoVCSLayer(
                        posixpath.join(self.path(), layer.name),
                        layer.name,
                        layer.geometry_column,
                        layer.key_column,
                        layer.geometry_type,
                    ),
                )

                items.append(item)
                QgsMessageLog.logMessage(
                    f"Layer '{item.geovcs_layer.name}' of type "
                    f"'{item.geovcs_layer.layer_type.name}' loaded from "
                    f"'{item.geovcs_layer.uri}'",
                    "GeoVCS",
                    Qgis.MessageLevel.Success,
                )
        except Exception as exception:  # noqa: BLE001 - browser must not crash
            QgsMessageLog.logMessage(
                f"Unable to list GeoVCS layers: {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            try:
                iface.messageBar().pushMessage(
                    "GeoVCS - Unable to Load Layers",
                    f"{type(exception).__name__}: {exception}",
                    Qgis.MessageLevel.Critical,
                    10,
                )
            except Exception:  # noqa: BLE001 - iface may be unavailable
                pass
            items = []

        self.setState(Qgis.BrowserItemState.Populated)
        return items


class GeoVCSProjectItem(QgsDataItem):
    def __init__(self, parent: QgsDataItem, name: str, path: str):
        super().__init__(Qgis.BrowserItemType.Custom, parent, name, path, PROVIDER_KEY)

        self.setIcon(QgsApplication.getThemeIcon("/mIconQgsProjectFile.svg"))

        self.setCapabilitiesV2(Qgis.BrowserItemCapability.NoCapabilities)
        self.setState(Qgis.BrowserItemState.Populated)

    def hasChildren(self):
        return False


class GeoVCSProjectGroupItem(QgsDataCollectionItem):
    def __init__(self, parent: QgsDataItem, path: str):
        super().__init__(parent, "Projects", path, PROVIDER_KEY)
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.Fertile)
        self.setIcon(QgsApplication.getThemeIcon("/mIconFolderProject.svg"))

    def createChildren(self) -> list[QgsDataItem]:  # type: ignore
        self.setState(Qgis.BrowserItemState.Populating)

        dummy_name = "[Empty]"
        dummy_path = posixpath.join(self.path(), dummy_name)
        dummy_item = GeoVCSProjectItem(self, dummy_name, dummy_path)

        self.setState(Qgis.BrowserItemState.Populated)

        return [dummy_item]


class GeoVCSConnectionsRootItem(QgsConnectionsRootItem):
    def __init__(self, parent):
        super().__init__(parent, PROVIDER_KEY, f"/{PROVIDER_KEY}", PROVIDER_KEY)
        self.setCapabilitiesV2(Qgis.BrowserItemCapability.Fertile)
        self._update_name()

    def _update_name(self):
        manager = GeoVCSConnectionManager()
        if manager.is_connected:
            self.setState(Qgis.BrowserItemState.NotPopulated)
            self.setName(
                f"GeoVCS at {manager.username}@{manager.database}/{manager.branch}"
            )
        else:
            self.setName("GeoVCS")
            self.setState(Qgis.BrowserItemState.Populated)

    def icon(self):
        return get_logo()

    def hasChildren(self):
        return GeoVCSConnectionManager().is_connected

    def refresh(self, children: list[QgsDataItem] | None = None) -> None:
        # The displayed name embeds the active branch, so refresh it before
        # asking the browser model to rebuild the children.
        self._update_name()
        return super().refresh()

    def depopulate(self) -> None:
        return super().depopulate()

    def createChildren(self) -> list[QgsDataItem]:  # type: ignore
        self._update_name()

        if not GeoVCSConnectionManager().is_connected:
            self.setState(Qgis.BrowserItemState.Populated)
            return []

        self.setState(Qgis.BrowserItemState.Populating)

        group_layers_path = posixpath.join(self.path(), "layers")
        group_layers_item = GeoVCSLayerGroupItem(self, group_layers_path)

        group_projects_path = posixpath.join(self.path(), "projects")
        group_projects_item = GeoVCSProjectGroupItem(self, group_projects_path)

        self.setState(Qgis.BrowserItemState.Populated)

        return [group_layers_item, group_projects_item]


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
            if not GeoVCSConnectionManager().is_connected:
                action_connect = QAction(
                    QgsApplication.getThemeIcon("/repositoryConnected.svg"),
                    "Connect...",
                    menu,
                )
                action_connect.triggered.connect(lambda: self._manage_connection(item))
                menu.addAction(action_connect)

            if GeoVCSConnectionManager().is_connected:
                action_edit = QAction(
                    QgsApplication.getThemeIcon("/mActionToggleEditing.svg"),
                    "Edit...",
                    menu,
                )
                action_edit.triggered.connect(lambda: self._manage_connection(item))
                menu.addAction(action_edit)

                action_refresh = QAction(
                    QgsApplication.getThemeIcon("/mActionRefresh.svg"),
                    "Refresh",
                    menu,
                )
                action_refresh.triggered.connect(lambda: self._refresh(item))
                menu.addAction(action_refresh)

                action_history = QAction(
                    QgsApplication.getThemeIcon("/mIconQueryHistory.svg"),
                    "History...",
                    menu,
                )
                action_history.triggered.connect(lambda: self._history(item))
                menu.addAction(action_history)

                action_disconnect = QAction(
                    QgsApplication.getThemeIcon("/mActionRemove.svg"),
                    "Disconnect",
                    menu,
                )
                action_disconnect.triggered.connect(lambda: self._disconnect(item))
                menu.addAction(action_disconnect)

    def _refresh(self, item: GeoVCSConnectionsRootItem):
        item.refresh()

    @staticmethod
    def _refresh_version_manager():
        """Ask any open Version Manager dock to reload after connect/disconnect."""
        refresh_version_manager_dock()

    def _manage_connection(self, item: GeoVCSConnectionsRootItem):
        manager = GeoVCSConnectionManager()
        was_connected = manager.is_connected

        if was_connected:
            current = GeoVCSConnection(
                host=manager.host or "",
                port=manager.port or "",
                database=manager.database or "",
                branch=manager.branch or "",
                auth_config_id=manager.auth_config_id or "",
            )
            connection, ok = GeoVCSDialogConnectionEdit.execute_for(current)
        else:
            connection, ok = GeoVCSDialogConnectionCreate.execute()

        if not ok or not connection:
            return

        try:
            manager.connect(connection)
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            QgsMessageLog.logMessage(
                f"Database connection failed: {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            try:
                iface.messageBar().pushMessage(
                    "GeoVCS - Connection Failed",
                    f"{type(exception).__name__}: {exception}",
                    Qgis.MessageLevel.Critical,
                    10,
                )
            except Exception:  # noqa: BLE001 - iface may be unavailable
                pass
            item.refresh()
            return

        try:
            iface.messageBar().pushMessage(  # type: ignore
                "GeoVCS - Connection Updated"
                if was_connected
                else "GeoVCS - Connection Created",
                f"Database connection '{connection.connection_string}' "
                f"{'updated' if was_connected else 'created'} successfully.",
                Qgis.MessageLevel.Success,
            )
        except Exception:  # noqa: BLE001 - iface may be unavailable
            pass
        item.refresh()
        self._refresh_version_manager()

    def _disconnect(self, item: GeoVCSConnectionsRootItem):
        try:
            GeoVCSConnectionManager().disconnect()
        except Exception as exception:  # noqa: BLE001 - surfaced to the user
            QgsMessageLog.logMessage(
                f"Failed to disconnect: {exception}",
                "GeoVCS",
                Qgis.MessageLevel.Critical,
            )
            return

        try:
            iface.messageBar().pushMessage(  # type: ignore
                "GeoVCS - Disconnected",
                "Database disconnected successfully.",
                Qgis.MessageLevel.Success,
            )
        except Exception:  # noqa: BLE001 - iface may be unavailable
            pass
        item.depopulate()
        item.refresh()
        self._refresh_version_manager()

    def _history(self, item: GeoVCSConnectionsRootItem):
        dialog = GeoVCSDialogHistory()
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        finally:
            dialog.deleteLater()
        item.refresh()
