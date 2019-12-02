# Copyright (c) 2017 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin
from UM.Logger import Logger
from UM.Application import Application
from UM.Signal import Signal, signalemitter
from UM.Version import Version

from . import ClusterUM3OutputDevice, LegacyUM3OutputDevice

from PyQt5.QtNetwork import QNetworkRequest, QNetworkAccessManager
from PyQt5.QtCore import QUrl

from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo
from queue import Queue
from threading import Event, Thread
from time import time

import json


##      This plugin handles the connection detection & creation of output device objects for the UM3 printer.
#       Zero-Conf is used to detect printers, which are saved in a dict.
#       If we discover a printer that has the same key as the active machine instance a connection is made.
@signalemitter
class UM3OutputDevicePlugin(OutputDevicePlugin):
    addDeviceSignal = Signal()
    removeDeviceSignal = Signal()
    discoveredDevicesChanged = Signal()

    def __init__(self):
        super().__init__()
        self._zero_conf = None
        self._zero_conf_browser = None

        # Because the model needs to be created in the same thread as the QMLEngine, we use a signal.
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

        # Get list of manual instances from preferences
        self._preferences = Application.getInstance().getPreferences()
        self._preferences.addPreference("um3networkprinting/manual_instances",
                                        "")  # A comma-separated list of ip adresses or hostnames

        self._manual_instances = self._preferences.getValue("um3networkprinting/manual_instances").split(",")

        # Store the last manual entry key
        self._last_manual_entry_key = "" # type: str

        # The zero-conf service changed requests are handled in a separate thread, so we can re-schedule the requests
        # which fail to get detailed service info.
        # Any new or re-scheduled requests will be appended to the request queue, and the handling thread will pick
        # them up and process them.
        self._service_changed_request_queue = Queue()
        self._service_changed_request_event = Event()
        self._service_changed_request_thread = Thread(target=self._handleOnServiceChangedRequests, daemon=True)
        self._service_changed_request_thread.start()

    def getDiscoveredDevices(self):
        return self._discovered_devices

    def getLastManualDevice(self) -> str:
        return self._last_manual_entry_key

    def resetLastManualDevice(self) -> None:
        self._last_manual_entry_key = ""

    ##  Start looking for devices on network.
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
        self._zero_conf_browser = ServiceBrowser(self._zero_conf, u'_ultimaker._tcp.local.',
                                                 [self._appendServiceChangedRequest])

        # Look for manual instances from preference
        for address in self._manual_instances:
            if address:
                self.addManualDevice(address)
        self.resetLastManualDevice()

    def reCheckConnections(self):
        active_machine = Application.getInstance().getGlobalContainerStack()
        if not active_machine:
            return

        um_network_key = active_machine.getMetaDataEntry("um_network_key")

        for key in self._discovered_devices:
            if key == um_network_key:
                if not self._discovered_devices[key].isConnected():
                    Logger.log("d", "Attempting to connect with [%s]" % key)
                    self._discovered_devices[key].connect()
                    self._discovered_devices[key].connectionStateChanged.connect(self._onDeviceConnectionStateChanged)
                else:
                    self._onDeviceConnectionStateChanged(key)
            else:
                if self._discovered_devices[key].isConnected():
                    Logger.log("d", "Attempting to close connection with [%s]" % key)
                    self._discovered_devices[key].close()
                    self._discovered_devices[key].connectionStateChanged.disconnect(self._onDeviceConnectionStateChanged)

    def _onDeviceConnectionStateChanged(self, key):
        if key not in self._discovered_devices:
            return
        if self._discovered_devices[key].isConnected():
            # Sometimes the status changes after changing the global container and maybe the device doesn't belong to this machine
            um_network_key = Application.getInstance().getGlobalContainerStack().getMetaDataEntry("um_network_key")
            if key == um_network_key:
                self.getOutputDeviceManager().addOutputDevice(self._discovered_devices[key])
        else:
            self.getOutputDeviceManager().removeOutputDevice(key)

    def stop(self):
        if self._zero_conf is not None:
            Logger.log("d", "zeroconf close...")
            self._zero_conf.close()

    def removeManualDevice(self, key, address = None):
        if key in self._discovered_devices:
            if not address:
                address = self._discovered_devices[key].ipAddress
            self._onRemoveDevice(key)
            self.resetLastManualDevice()

        if address in self._manual_instances:
            self._manual_instances.remove(address)
            self._preferences.setValue("um3networkprinting/manual_instances", ",".join(self._manual_instances))

    def addManualDevice(self, address):
        if address not in self._manual_instances:
            self._manual_instances.append(address)
            self._preferences.setValue("um3networkprinting/manual_instances", ",".join(self._manual_instances))

        instance_name = "manual:%s" % address
        properties = {
            b"name": address.encode("utf-8"),
            b"address": address.encode("utf-8"),
            b"manual": b"true",
            b"incomplete": b"true",
            b"temporary": b"true"   # Still a temporary device until all the info is retrieved in _onNetworkRequestFinished
        }

        if instance_name not in self._discovered_devices:
            # Add a preliminary printer instance
            self._onAddDevice(instance_name, address, properties)
        self._last_manual_entry_key = instance_name

        self._checkManualDevice(address)

    def _checkManualDevice(self, address):
        # Check if a UM3 family device exists at this address.
        # If a printer responds, it will replace the preliminary printer created above
        # origin=manual is for tracking back the origin of the call
        url = QUrl("http://" + address + self._api_prefix + "system")
        name_request = QNetworkRequest(url)
        self._network_manager.get(name_request)

    def _onNetworkRequestFinished(self, reply):
        reply_url = reply.url().toString()

        if "system" in reply_url:
            if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 200:
                # Something went wrong with checking the firmware version!
                return

            try:
                system_info = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except:
                Logger.log("e", "Something went wrong converting the JSON.")
                return

            address = reply.url().host()
            has_cluster_capable_firmware = Version(system_info["firmware"]) > self._min_cluster_version
            instance_name = "manual:%s" % address
            properties = {
                b"name": (system_info["name"] + " (manual)").encode("utf-8"),
                b"address": address.encode("utf-8"),
                b"firmware_version": system_info["firmware"].encode("utf-8"),
                b"manual": b"true",
                b"machine": str(system_info['hardware']["typeid"]).encode("utf-8")
            }

            if has_cluster_capable_firmware:
                # Cluster needs an additional request, before it's completed.
                properties[b"incomplete"] = b"true"

            # Check if the device is still in the list & re-add it with the updated
            # information.
            if instance_name in self._discovered_devices:
                self._onRemoveDevice(instance_name)
                self._onAddDevice(instance_name, address, properties)

            if has_cluster_capable_firmware:
                # We need to request more info in order to figure out the size of the cluster.
                cluster_url = QUrl("http://" + address + self._cluster_api_prefix + "printers/")
                cluster_request = QNetworkRequest(cluster_url)
                self._network_manager.get(cluster_request)

        elif "printers" in reply_url:
            if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 200:
                # Something went wrong with checking the amount of printers the cluster has!
                return
            # So we confirmed that the device is in fact a cluster printer, and we should now know how big it is.
            try:
                cluster_printers_list = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except:
                Logger.log("e", "Something went wrong converting the JSON.")
                return
            address = reply.url().host()
            instance_name = "manual:%s" % address
            if instance_name in self._discovered_devices:
                device = self._discovered_devices[instance_name]
                properties = device.getProperties().copy()
                if b"incomplete" in properties:
                    del properties[b"incomplete"]
                properties[b'cluster_size'] = len(cluster_printers_list)
                self._onRemoveDevice(instance_name)
                self._onAddDevice(instance_name, address, properties)

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
        cluster_size = int(properties.get(b"cluster_size", -1))

        printer_type = properties.get(b"machine", b"").decode("utf-8")
        printer_type_identifiers = {
            "9066": "ultimaker3",
            "9511": "ultimaker3_extended",
            "9051": "ultimaker_s5"
        }

        for key, value in printer_type_identifiers.items():
            if printer_type.startswith(key):
                properties[b"printer_type"] = bytes(value, encoding="utf8")
                break
        else:
            properties[b"printer_type"] = b"Unknown"
        if cluster_size >= 0:
            device = ClusterUM3OutputDevice.ClusterUM3OutputDevice(name, address, properties)
        else:
            device = LegacyUM3OutputDevice.LegacyUM3OutputDevice(name, address, properties)

        self._discovered_devices[device.getId()] = device
        self.discoveredDevicesChanged.emit()

        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if global_container_stack and device.getId() == global_container_stack.getMetaDataEntry("um_network_key"):
            device.connect()
            device.connectionStateChanged.connect(self._onDeviceConnectionStateChanged)

    ##  Appends a service changed request so later the handling thread will pick it up and processes it.
    def _appendServiceChangedRequest(self, zeroconf, service_type, name, state_change):
        # append the request and set the event so the event handling thread can pick it up
        item = (zeroconf, service_type, name, state_change)
        self._service_changed_request_queue.put(item)
        self._service_changed_request_event.set()

    def _handleOnServiceChangedRequests(self):
        while True:
            # Wait for the event to be set
            self._service_changed_request_event.wait(timeout = 5.0)

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

    ##  Handler for zeroConf detection.
    #   Return True or False indicating if the process succeeded.
    #   Note that this function can take over 3 seconds to complete. Be carefull calling it from the main thread.
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
                type_of_device = info.properties.get(b"type", None)
                if type_of_device:
                    if type_of_device == b"printer":
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