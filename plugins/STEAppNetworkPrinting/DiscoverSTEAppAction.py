import os.path
import time
from typing import cast, Optional

from PyQt5.QtCore import pyqtSignal, pyqtProperty, pyqtSlot, QObject

from UM.PluginRegistry import PluginRegistry
from UM.Logger import Logger
from UM.i18n import i18nCatalog

from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.MachineAction import MachineAction

from .STEAppOutputDevicePlugin import STEAppOutputDevicePlugin

catalog = i18nCatalog("steslicer")

class DiscoverSTEAppActions (MachineAction):
    discoveredDevicesChanged = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("DiscoverSTEAppAction", catalog.i18nc("@action", "Connect via Network"))
        self._qml_url = "resources/qml/DiscoverSTEAppAction.qml"

        self._network_plugin = None  

        self.__additional_components_view = None  # type: Optional[QObject]

        SteSlicerApplication.getInstance().engineCreatedSignal.connect(self._createAdditionalComponentsView)

        self._last_zero_conf_event_time = time.time()  # type: float

        # Time to wait after a zero-conf service change before allowing a zeroconf reset
        self._zero_conf_change_grace_period = 0.25  # type: float

    @pyqtSlot()
    def startDiscovery(self):
        if not self._network_plugin:
            Logger.log("d", "Starting device discovery.")
            self._network_plugin = SteSlicerApplication.getInstance().getOutputDeviceManager().getOutputDevicePlugin(
                "STEAppNetworkPrinting")
            self._network_plugin.discoveredDevicesChanged.connect(self._onDeviceDiscoveryChanged)
            self.discoveredDevicesChanged.emit()

    @pyqtSlot()
    def reset(self):
        Logger.log("d", "Reset the list of found devices.")
        if self._network_plugin:
            self._network_plugin.resetLastManualDevice()
        self.discoveredDevicesChanged.emit()

    @pyqtSlot()
    def restartDiscovery(self):
        if time.time() - self._last_zero_conf_event_time > self._zero_conf_change_grace_period:
            if not self._network_plugin:
                self.startDiscovery()
            else:
                self._network_plugin.startDiscovery()       

    @pyqtSlot(str, str)
    def removeManualDevice(self, key, address):
        if not self._network_plugin:
            return

        self._network_plugin.removeManualDevice(key, address)                

    @pyqtSlot(str, str)
    def setManualDevice(self, key, address):
        if key != "":
            # This manual printer replaces a current manual printer
            self._network_plugin.removeManualDevice(key)

        if address != "":
            self._network_plugin.addManualDevice(address)

    def _onDeviceDiscoveryChanged(self, *args):
        self._last_zero_conf_event_time = time.time()
        self.discoveredDevicesChanged.emit()        

    @pyqtProperty("QVariantList", notify=discoveredDevicesChanged)
    def foundDevices(self):
        if self._network_plugin:

            printers = list(self._network_plugin.getDiscoveredDevices().values())
            printers.sort(key=lambda k: k.name)
            return printers
        else:
            return []       