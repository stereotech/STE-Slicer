# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from UM.Application import Application
from UM.Message import Message
from UM.Logger import Logger
from UM.Job import Job
from UM.Version import Version

import urllib.request
from urllib.error import URLError
from typing import Dict, Optional

from .FirmwareUpdateCheckerLookup import FirmwareUpdateCheckerLookup, getSettingsKeyForMachine
from .FirmwareUpdateCheckerMessage import FirmwareUpdateCheckerMessage

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("cura")


##  This job checks if there is an update available on the provided URL.
class FirmwareUpdateCheckerJob(Job):
    STRING_ZERO_VERSION = "0.0.0"
    STRING_EPSILON_VERSION = "0.0.1"
    ZERO_VERSION = Version(STRING_ZERO_VERSION)
    EPSILON_VERSION = Version(STRING_EPSILON_VERSION)

    def __init__(self, container, silent, machine_name, metadata, callback) -> None:
        super().__init__()
        self._container = container
        self.silent = silent
        self._callback = callback

        self._machine_name = machine_name
        self._metadata = metadata
        self._lookups = None  # type:Optional[FirmwareUpdateCheckerLookup]
        self._headers = {}  # type:Dict[str, str]  # Don't set headers yet.

    def getUrlResponse(self, url: str) -> str:
        result = self.STRING_ZERO_VERSION

        try:
            request = urllib.request.Request(url, headers = self._headers)
            response = urllib.request.urlopen(request)
            result = response.read().decode("utf-8")
        except URLError:
            Logger.log("w", "Could not reach '{0}', if this URL is old, consider removal.".format(url))

        return result

    def parseVersionResponse(self, response: str) -> Version:
        raw_str = response.split("\n", 1)[0].rstrip()
        return Version(raw_str)

    def getCurrentVersion(self) -> Version:
        max_version = self.ZERO_VERSION
        if self._lookups is None:
            return max_version

        machine_urls = self._lookups.getCheckUrls()
        if machine_urls is not None:
            for url in machine_urls:
                version = self.parseVersionResponse(self.getUrlResponse(url))
                if version > max_version:
                    max_version = version

        if max_version < self.EPSILON_VERSION:
            Logger.log("w", "MachineID {0} not handled!".format(self._lookups.getMachineName()))

        return max_version

    def run(self):
        if self._lookups is None:
            self._lookups = FirmwareUpdateCheckerLookup(self._machine_name, self._metadata)

        try:
            # Initialize a Preference that stores the last version checked for this printer.
            Application.getInstance().getPreferences().addPreference(
                getSettingsKeyForMachine(self._lookups.getMachineId()), "")

            # Get headers
            application_name = Application.getInstance().getApplicationName()
            application_version = Application.getInstance().getVersion()
            self._headers = {"User-Agent": "%s - %s" % (application_name, application_version)}

            # get machine name from the definition container
            machine_name = self._container.definition.getName()

            # If it is not None, then we compare between the checked_version and the current_version
            machine_id = self._lookups.getMachineId()
            if machine_id is not None:
                Logger.log("i", "You have a(n) {0} in the printer list. Let's check the firmware!".format(machine_name))

                current_version = self.getCurrentVersion()

                # If it is the first time the version is checked, the checked_version is ""
                setting_key_str = getSettingsKeyForMachine(machine_id)
                checked_version = Version(Application.getInstance().getPreferences().getValue(setting_key_str))

                # If the checked_version is "", it's because is the first time we check firmware and in this case
                # we will not show the notification, but we will store it for the next time
                Application.getInstance().getPreferences().setValue(setting_key_str, current_version)
                Logger.log("i", "Reading firmware version of %s: checked = %s - latest = %s", machine_name, checked_version, current_version)

                # The first time we want to store the current version, the notification will not be shown,
                # because the new version of Cura will be release before the firmware and we don't want to
                # notify the user when no new firmware version is available.
                if (checked_version != "") and (checked_version != current_version):
                    Logger.log("i", "SHOWING FIRMWARE UPDATE MESSAGE")
                    message = FirmwareUpdateCheckerMessage(machine_id, machine_name, self._lookups.getRedirectUserUrl())
                    message.actionTriggered.connect(self._callback)
                    message.show()
            else:
                Logger.log("i", "No machine with name {0} in list of firmware to check.".format(machine_name))

        except Exception as e:
            Logger.log("w", "Failed to check for new version: %s", e)
            if not self.silent:
                Message(i18n_catalog.i18nc("@info", "Could not access update information.")).show()
            return
