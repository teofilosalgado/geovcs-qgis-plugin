from qgis.core import QgsApplication
from qgis.gui import QgisInterface, QgsGui
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QToolBar

from geovcs.src.browser import GeoVCSDataItemGuiProvider, GeoVCSDataItemProvider
from geovcs.src.form.dock_version_manager import GeoVCSDockVersionManagerDock
from geovcs.src.model import GeoVCSConnectionManager
from geovcs.src.util import get_logo


class GeoVCS:
    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.toolbar: QToolBar | None = None
        self.action_show_dock = None

        self.data_item_provider: GeoVCSDataItemProvider | None = None
        self.data_item_gui_provider: GeoVCSDataItemGuiProvider | None = None
        self.dock_version_manager: GeoVCSDockVersionManagerDock | None = None

    def initGui(self):
        # The connection manager is a process-wide singleton, so after a
        # disable/enable cycle it already exists but its datasource was closed
        # during unload. Restore the saved connection explicitly.
        try:
            GeoVCSConnectionManager().restore()
        except Exception:  # noqa: BLE001 - plugin must still load
            pass

        self.toolbar = self.iface.addToolBar("GeoVCS")
        if self.toolbar:
            self.toolbar.setObjectName("GeoVCS")

        self.data_item_provider = GeoVCSDataItemProvider()
        QgsApplication.dataItemProviderRegistry().addProvider(self.data_item_provider)  # type: ignore

        self.data_item_gui_provider = GeoVCSDataItemGuiProvider()
        QgsGui.dataItemGuiProviderRegistry().addProvider(self.data_item_gui_provider)  # type: ignore

        self.dock_version_manager = GeoVCSDockVersionManagerDock()
        self.dock_version_manager.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.iface.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.dock_version_manager
        )

        self.action_show_dock = self.dock_version_manager.toggleViewAction()
        if self.action_show_dock and self.toolbar:
            self.action_show_dock.setText("Version Manager")
            self.action_show_dock.setIcon(
                QgsApplication.getThemeIcon("/dependencies.svg")
            )
            self.toolbar.addAction(self.action_show_dock)

        self.iface.addPluginToMenu("&GeoVCS", self.action_show_dock)
        plugin_menu = self.iface.pluginMenu()
        if plugin_menu:
            for action in plugin_menu.actions():
                if action.text() != "&GeoVCS":
                    continue
                action.setIcon(get_logo())

    def unload(self):
        main_window = self.iface.mainWindow()
        data_item_provider_registry = QgsApplication.dataItemProviderRegistry()
        data_item_gui_provider_registry = QgsGui.dataItemGuiProviderRegistry()

        if self.action_show_dock:
            self.iface.removePluginMenu("&GeoVCS", self.action_show_dock)
        if self.toolbar and main_window:
            if self.action_show_dock:
                self.toolbar.removeAction(self.action_show_dock)
            main_window.removeToolBar(self.toolbar)
            self.toolbar = None

        if self.dock_version_manager:
            self.iface.removeDockWidget(self.dock_version_manager)
            self.dock_version_manager.deleteLater()
            self.dock_version_manager = None

        if self.data_item_provider and data_item_provider_registry:
            data_item_provider_registry.removeProvider(self.data_item_provider)
            self.data_item_provider = None

        if self.data_item_gui_provider and data_item_gui_provider_registry:
            data_item_gui_provider_registry.removeProvider(self.data_item_gui_provider)
            self.data_item_gui_provider = None

        # Release the GDAL dataset (and therefore the MySQL session) without
        # deleting the saved connection settings.
        try:
            GeoVCSConnectionManager().close()
        except Exception:  # noqa: BLE001 - unloading must always finish
            pass
