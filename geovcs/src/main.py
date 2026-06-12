from qgis.core import QgsApplication
from qgis.gui import QgisInterface, QgsGui
from qgis.PyQt.QtCore import Qt

from geovcs.src.browser import GeoVCSDataItemGuiProvider, GeoVCSDataItemProvider
from geovcs.src.form.dock_version_manager import GeoVCSDockVersionManagerDock
from geovcs.src.util import get_logo


class GeoVCS:
    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.toolbar = None
        self.action_show_dock = None

        self.data_item_provider: GeoVCSDataItemProvider = None
        self.data_item_gui_provider: GeoVCSDataItemGuiProvider = None
        self.dock_version_manager: GeoVCSDockVersionManagerDock = None

    def initGui(self):
        self.toolbar = self.iface.addToolBar("GeoVCS")
        self.toolbar.setObjectName("GeoVCS")

        self.data_item_provider = GeoVCSDataItemProvider()
        QgsApplication.dataItemProviderRegistry().addProvider(self.data_item_provider)

        self.data_item_gui_provider = GeoVCSDataItemGuiProvider()
        QgsGui.dataItemGuiProviderRegistry().addProvider(self.data_item_gui_provider)

        self.dock_version_manager = GeoVCSDockVersionManagerDock()
        self.dock_version_manager.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.iface.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.dock_version_manager
        )

        self.action_show_dock = self.dock_version_manager.toggleViewAction()
        self.action_show_dock.setText("Version Manager")
        self.action_show_dock.setIcon(
            QgsApplication.getThemeIcon("/mIconQueryHistory.svg")
        )
        self.toolbar.addAction(self.action_show_dock)

        self.iface.addPluginToMenu("&GeoVCS", self.action_show_dock)
        for action in self.iface.pluginMenu().actions():
            if action.text() != "&GeoVCS":
                continue
            action.setIcon(get_logo())

    def unload(self):
        self.iface.removePluginMenu("&GeoVCS", self.action_show_dock)
        if self.toolbar:
            self.toolbar.removeAction(self.action_show_dock)
            self.iface.mainWindow().removeToolBar(self.toolbar)

        if self.dock_version_manager:
            self.iface.removeDockWidget(self.dock_version_manager)
            self.dock_version_manager.deleteLater()

        if self.data_item_provider:
            QgsApplication.dataItemProviderRegistry().removeProvider(
                self.data_item_provider
            )
            self.data_item_provider = None

        if self.data_item_gui_provider:
            QgsGui.dataItemGuiProviderRegistry().removeProvider(
                self.data_item_gui_provider
            )
            self.data_item_gui_provider = None
