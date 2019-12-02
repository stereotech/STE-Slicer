# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from PyQt5.QtCore import pyqtProperty, QObject, pyqtSignal
from typing import List

MYPY = False
if MYPY:
    from cura.PrinterOutput.ExtruderConfigurationModel import ExtruderConfigurationModel


class ConfigurationModel(QObject):

    configurationChanged = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._printer_type = ""
        self._extruder_configurations = []     # type: List[ExtruderConfigurationModel]
        self._buildplate_configuration = ""

    def setPrinterType(self, printer_type):
        self._printer_type = printer_type

    @pyqtProperty(str, fset = setPrinterType, notify = configurationChanged)
    def printerType(self) -> str:
        return self._printer_type

    def setExtruderConfigurations(self, extruder_configurations: List["ExtruderConfigurationModel"]):
        if self._extruder_configurations != extruder_configurations:
            self._extruder_configurations = extruder_configurations

            for extruder_configuration in self._extruder_configurations:
                extruder_configuration.extruderConfigurationChanged.connect(self.configurationChanged)

            self.configurationChanged.emit()

    @pyqtProperty("QVariantList", fset = setExtruderConfigurations, notify = configurationChanged)
    def extruderConfigurations(self):
        return self._extruder_configurations

    def setBuildplateConfiguration(self, buildplate_configuration: str) -> None:
        self._buildplate_configuration = buildplate_configuration

    @pyqtProperty(str, fset = setBuildplateConfiguration, notify = configurationChanged)
    def buildplateConfiguration(self) -> str:
        return self._buildplate_configuration

    ##  This method is intended to indicate whether the configuration is valid or not.
    #   The method checks if the mandatory fields are or not set
    def isValid(self) -> bool:
        if not self._extruder_configurations:
            return False
        for configuration in self._extruder_configurations:
            if configuration is None:
                return False
        return self._printer_type is not None

    def __str__(self):
        message_chunks = []
        message_chunks.append("Printer type: " + self._printer_type)
        message_chunks.append("Extruders: [")
        for configuration in self._extruder_configurations:
            message_chunks.append("   " + str(configuration))
        message_chunks.append("]")
        if self._buildplate_configuration is not None:
            message_chunks.append("Buildplate: " + self._buildplate_configuration)

        return "\n".join(message_chunks)

    def __eq__(self, other):
        return hash(self) == hash(other)

    ##  The hash function is used to compare and create unique sets. The configuration is unique if the configuration
    #   of the extruders is unique (the order of the extruders matters), and the type and buildplate is the same.
    def __hash__(self):
        extruder_hash = hash(0)
        first_extruder = None
        for configuration in self._extruder_configurations:
            extruder_hash ^= hash(configuration)
            if configuration.position == 0:
                first_extruder = configuration
        # To ensure the correct order of the extruders, we add an "and" operation using the first extruder hash value
        if first_extruder:
            extruder_hash &= hash(first_extruder)

        return hash(self._printer_type) ^ extruder_hash ^ hash(self._buildplate_configuration)