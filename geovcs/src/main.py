from qgis.core import QgsApplication
from qgis.gui import QgisInterface, QgsGui
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QToolBar

from geovcs.src.browser import GeoVCSDataItemGuiProvider, GeoVCSDataItemProvider
from geovcs.src.form.dock_version_manager import GeoVCSDockVersionManagerDock
from geovcs.src.util import get_logo


class GeoVCS:
    def __init__(self, iface: QgisInterface):
        # os.environ["MYSQL_PWD"] = "gis"

        self.iface = iface
        self.toolbar: QToolBar | None = None
        self.action_show_dock = None

        self.data_item_provider: GeoVCSDataItemProvider | None = None
        self.data_item_gui_provider: GeoVCSDataItemGuiProvider | None = None
        self.dock_version_manager: GeoVCSDockVersionManagerDock | None = None

    def initGui(self):
        data_item_provider_registry = QgsApplication.dataItemProviderRegistry()
        data_item_gui_provider_registry = QgsGui.dataItemGuiProviderRegistry()
        plugin_menu = self.iface.pluginMenu()

        self.toolbar = self.iface.addToolBar("GeoVCS")
        if self.toolbar:
            self.toolbar.setObjectName("GeoVCS")

        self.data_item_provider = GeoVCSDataItemProvider()
        if self.data_item_gui_provider and data_item_provider_registry:
            data_item_provider_registry.addProvider(self.data_item_provider)

        self.data_item_gui_provider = GeoVCSDataItemGuiProvider()
        if self.data_item_gui_provider and data_item_gui_provider_registry:
            data_item_gui_provider_registry.addProvider(self.data_item_gui_provider)

        self.dock_version_manager = GeoVCSDockVersionManagerDock()
        self.dock_version_manager.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.iface.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.dock_version_manager
        )

        self.action_show_dock = self.dock_version_manager.toggleViewAction()
        if self.action_show_dock and self.toolbar:
            self.action_show_dock.setText("Version Manager")
            self.action_show_dock.setIcon(
                QgsApplication.getThemeIcon("/mIconQueryHistory.svg")
            )
            self.toolbar.addAction(self.action_show_dock)

        self.iface.addPluginToMenu("&GeoVCS", self.action_show_dock)
        if plugin_menu:
            for action in plugin_menu.actions():
                if action.text() != "&GeoVCS":
                    continue
                action.setIcon(get_logo())

    def unload(self):
        main_window = self.iface.mainWindow()
        data_item_provider_registry = QgsApplication.dataItemProviderRegistry()
        data_item_gui_provider_registry = QgsGui.dataItemGuiProviderRegistry()

        self.iface.removePluginMenu("&GeoVCS", self.action_show_dock)
        if self.toolbar and main_window:
            self.toolbar.removeAction(self.action_show_dock)
            main_window.removeToolBar(self.toolbar)

        if self.dock_version_manager:
            self.iface.removeDockWidget(self.dock_version_manager)
            self.dock_version_manager.deleteLater()

        if self.data_item_provider and data_item_provider_registry:
            data_item_provider_registry.removeProvider(self.data_item_provider)
            self.data_item_provider = None

        if self.data_item_gui_provider and data_item_gui_provider_registry:
            data_item_gui_provider_registry.removeProvider(self.data_item_gui_provider)
            self.data_item_gui_provider = None
