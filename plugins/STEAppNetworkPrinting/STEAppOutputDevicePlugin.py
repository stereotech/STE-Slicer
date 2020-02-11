from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin
from UM.Logger import Logger
from UM.Application import Application
from UM.Signal import Signal, signalemitter
from UM.Version import Version
import re

from . import LegacySTEAppOutputDevice

from PyQt5.QtNetwork import QNetworkRequest, QNetworkAccessManager
from PyQt5.QtCore import QUrl

from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo
from queue import Queue
from threading import Event, Thread
from time import time

import json

@signalemitter
class STEAppOutputDevicePlugin(OutputDevicePlugin):
    addDeviceSignal = Signal()
    removeDeviceSignal = Signal()
    discoveredDevicesChanged = Signal()

    def __init__(self):
        super().__init__()
        self._zero_conf = None
        self._zero_conf_browser = None

        self.addDeviceSignal.connect(self._onAddDevice)
        self.removeDeviceSignal.connect(self._onRemoveDevice)

        Application.getInstance().globalContainerStackChanged.connect(self.reCheckConnections)

        self._discovered_devices = {}
        
        self._network_manager = QNetworkAccessManager()
        self._network_manager.finished.connect(self._onNetworkRequestFinished)

        self._min_cluster_version = Version("4.0.0")

        self._api_version = "1"
        self._api_prefix = "/api/v" + self._api_version + "/"
        self._cluster_api_version = "1"
        self._cluster_api_prefix = "/cluster-api/v" + self._cluster_api_version + "/"

        self._preferences = Application.getInstance().getPreferences()
        self._preferences.addPreference("steappnetworkprinting/manual_instances",
                                        "") 

        self._manual_instances = self._preferences.getValue("steappnetworkprinting/manual_instances").split(",")

        self._last_manual_entry_key = ""

    def getDiscoveredDevices(self):
        return self._discovered_devices

    def getLastManualDevice(self) -> str:
        return self._last_manual_entry_key

    def resetLastManualDevice(self) -> None:
        self._last_manual_entry_key = ""

    def start(self):
        self.startDiscovery()

    def startDiscovery(self):
        self.stop()
        if self._zero_conf_browser:
            self._zero_conf_browser.cancel()
            self._zero_conf_browser = None  # Force the old ServiceBrowser to be destroyed.

        for instance_name in list(self._discovered_devices):
            self._onRemoveDevice(instance_name)

        self._zero_conf = Zeroconf()
        self._zero_conf_browser = ServiceBrowser(self._zero_conf, u'_stereotech._tcp.local.',
                                                [self._appendServiceChangedRequest])

        # Look for manual instances from preference
        for address in self._manual_instances:
            if address:
                self.addManualDevice(address)
        self.resetLastManualDevice()



    def _checkManualDevice(self, address):
        # Check if a UM3 family device exists at this address.
        # If a printer responds, it will replace the preliminary printer created above
        # origin=manual is for tracking back the origin of the call
        url = QUrl("http://" + address + self._api_prefix + "system")
        name_request = QNetworkRequest(url)
        self._network_manager.get(name_request)

    def _onRemoveDevice(self, device_id):
        device = self._discovered_devices.pop(device_id, None)
        if device:
            if device.isConnected():
                device.disconnect()
                try:
                    device.connectionStateChanged.disconnect(self._onDeviceConnectionStateChanged)
                except TypeError:
                    # Disconnect already happened.
                    pass

            self.discoveredDevicesChanged.emit()

    def _onAddDevice(self, name, address, properties):
        # Check what kind of device we need to add; Depending on the firmware we either add a "Connect"/"Cluster"
        # or "Legacy" UM3 device.
        cluster_size = int(properties.get(b"printers", 1))

        printer_type = properties.get(b"model", b"").decode("utf-8")
        printer_type_identifiers = {
            "STE330": "ste320",
            "STE520": "ste520"
        }

        for key, value in printer_type_identifiers.items():
            if printer_type.startswith(key):
                properties[b"printer_type"] = bytes(value, encoding="utf8")
                break
        else:
            properties[b"printer_type"] = b"Unknown"

        device = LegacySTEAppOutputDevice.LegacySTEAppOutputDevice(name, address, properties)

        self._discovered_devices[device.getId()] = device
        self.discoveredDevicesChanged.emit()

        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if global_container_stack and device.getId() == global_container_stack.getMetaDataEntry("um_network_key"):
            device.connect()
            device.connectionStateChanged.connect(self._onDeviceConnectionStateChanged)

    def _appendServiceChangedRequest(self, zeroconf, service_type, name, state_change):
        # append the request and set the event so the event handling thread can pick it up
        item = (zeroconf, service_type, name, state_change)
        self._service_changed_request_queue.put(item)
        self._service_changed_request_event.set()

    def _handleOnServiceChangedRequests(self):
        while True:
            # Wait for the event to be set
            self._service_changed_request_event.wait(timeout=5.0)

            # Stop if the application is shutting down
            if Application.getInstance().isShuttingDown():
                return

            self._service_changed_request_event.clear()

            # Handle all pending requests
            reschedule_requests = []  # A list of requests that have failed so later they will get re-scheduled
            while not self._service_changed_request_queue.empty():
                request = self._service_changed_request_queue.get()
                zeroconf, service_type, name, state_change = request
                try:
                    result = self._onServiceChanged(zeroconf, service_type, name, state_change)
                    if not result:
                        reschedule_requests.append(request)
                except Exception:
                    Logger.logException("e", "Failed to get service info for [%s] [%s], the request will be rescheduled",
                                        service_type, name)
                    reschedule_requests.append(request)

            # Re-schedule the failed requests if any
            if reschedule_requests:
                for request in reschedule_requests:
                    self._service_changed_request_queue.put(request)

    def _onServiceChanged(self, zero_conf, service_type, name, state_change):
        if state_change == ServiceStateChange.Added:
            Logger.log("d", "Bonjour service added: %s" % name)

            # First try getting info from zero-conf cache
            info = ServiceInfo(service_type, name, properties={})
            for record in zero_conf.cache.entries_with_name(name.lower()):
                info.update_record(zero_conf, time(), record)

            for record in zero_conf.cache.entries_with_name(info.server):
                info.update_record(zero_conf, time(), record)
                if info.address:
                    break

            # Request more data if info is not complete
            if not info.address:
                Logger.log("d", "Trying to get address of %s", name)
                info = zero_conf.get_service_info(service_type, name)

            if info:
                type_of_device = str(info.properties.get(b"id", None), encoding='utf-8')
                if type_of_device:
                    if re.fullmatch(r'st-[a-z0-9]..', type_of_device):
                        address = '.'.join(map(lambda n: str(n), info.address))
                        self.addDeviceSignal.emit(str(name), address, info.properties)
                    else:
                        Logger.log("w",
                                   "The type of the found device is '%s', not 'printer'! Ignoring.." % type_of_device)
            else:
                Logger.log("w", "Could not get information about %s" % name)
                return False

        elif state_change == ServiceStateChange.Removed:
            Logger.log("d", "Bonjour service removed: %s" % name)
            self.removeDeviceSignal.emit(str(name))

        return True