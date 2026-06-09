from qgis.core import QgsApplication
from qgis.gui import QgisInterface, QgsGui
from qgis.PyQt.QtWidgets import QComboBox, QLabel

from geovcs.src.browser import GeoVCSDataItemGuiProvider, GeoVCSDataItemProvider


class GeoVCS:
    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.data_item_provider: GeoVCSDataItemProvider = None
        self.data_item_gui_provider: GeoVCSDataItemGuiProvider = None

    def initGui(self):
        self.data_item_provider = GeoVCSDataItemProvider()
        QgsApplication.dataItemProviderRegistry().addProvider(self.data_item_provider)

        self.data_item_gui_provider = GeoVCSDataItemGuiProvider()
        QgsGui.dataItemGuiProviderRegistry().addProvider(self.data_item_gui_provider)

        self.toolbar = self.iface.addToolBar("GeoVCS")
        self.toolbar.setObjectName("GeoVCS")

        self.branches_label = QLabel("Branch:")
        self.toolbar.addWidget(self.branches_label)

        self.branches_combo_box = QComboBox()
        self.branches_combo_box.setMinimumWidth(150)
        self.branches_combo_box.setDisabled(True)
        self.branches_combo_box.setToolTip("Select a GeoVCS branch for current layer.")
        self.toolbar.addWidget(self.branches_combo_box)

    def unload(self):
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
