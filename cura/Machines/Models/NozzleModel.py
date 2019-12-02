# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from PyQt5.QtCore import Qt

from UM.Application import Application
from UM.Logger import Logger
from UM.Qt.ListModel import ListModel
from UM.Util import parseBool

from cura.Machines.VariantType import VariantType


class NozzleModel(ListModel):
    IdRole = Qt.UserRole + 1
    HotendNameRole = Qt.UserRole + 2
    ContainerNodeRole = Qt.UserRole + 3

    def __init__(self, parent = None):
        super().__init__(parent)

        self.addRoleName(self.IdRole, "id")
        self.addRoleName(self.HotendNameRole, "hotend_name")
        self.addRoleName(self.ContainerNodeRole, "container_node")

        self._application = Application.getInstance()
        self._machine_manager = self._application.getMachineManager()
        self._variant_manager = self._application.getVariantManager()

        self._machine_manager.globalContainerChanged.connect(self._update)
        self._update()

    def _update(self):
        Logger.log("d", "Updating {model_class_name}.".format(model_class_name = self.__class__.__name__))

        self.items.clear()

        global_stack = self._machine_manager.activeMachine
        if global_stack is None:
            self.setItems([])
            return

        has_variants = parseBool(global_stack.getMetaDataEntry("has_variants", False))
        if not has_variants:
            self.setItems([])
            return

        variant_node_dict = self._variant_manager.getVariantNodes(global_stack, VariantType.NOZZLE)
        if not variant_node_dict:
            self.setItems([])
            return

        item_list = []
        for hotend_name, container_node in sorted(variant_node_dict.items(), key = lambda i: i[0].upper()):
            item = {"id": hotend_name,
                    "hotend_name": hotend_name,
                    "container_node": container_node
                    }

            item_list.append(item)

        self.setItems(item_list)
