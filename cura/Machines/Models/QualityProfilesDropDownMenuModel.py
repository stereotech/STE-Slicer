# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from PyQt5.QtCore import Qt

from UM.Application import Application
from UM.Logger import Logger
from UM.Qt.ListModel import ListModel
from UM.Settings.SettingFunction import SettingFunction

from cura.Machines.QualityManager import QualityGroup

#
# QML Model for all built-in quality profiles. This model is used for the drop-down quality menu.
#
class QualityProfilesDropDownMenuModel(ListModel):
    NameRole = Qt.UserRole + 1
    QualityTypeRole = Qt.UserRole + 2
    LayerHeightRole = Qt.UserRole + 3
    LayerHeightUnitRole = Qt.UserRole + 4
    AvailableRole = Qt.UserRole + 5
    QualityGroupRole = Qt.UserRole + 6
    QualityChangesGroupRole = Qt.UserRole + 7

    def __init__(self, parent = None):
        super().__init__(parent)

        self.addRoleName(self.NameRole, "name")
        self.addRoleName(self.QualityTypeRole, "quality_type")
        self.addRoleName(self.LayerHeightRole, "layer_height")
        self.addRoleName(self.LayerHeightUnitRole, "layer_height_unit")
        self.addRoleName(self.AvailableRole, "available") #Whether the quality profile is available in our current nozzle + material.
        self.addRoleName(self.QualityGroupRole, "quality_group")
        self.addRoleName(self.QualityChangesGroupRole, "quality_changes_group")

        self._application = Application.getInstance()
        self._machine_manager = self._application.getMachineManager()
        self._quality_manager = Application.getInstance().getQualityManager()

        self._application.globalContainerStackChanged.connect(self._update)
        self._machine_manager.activeQualityGroupChanged.connect(self._update)
        self._machine_manager.extruderChanged.connect(self._update)
        self._quality_manager.qualitiesUpdated.connect(self._update)

        self._layer_height_unit = ""  # This is cached

        self._update()

    def _update(self):
        Logger.log("d", "Updating {model_class_name}.".format(model_class_name = self.__class__.__name__))

        global_stack = self._machine_manager.activeMachine
        if global_stack is None:
            self.setItems([])
            Logger.log("d", "No active GlobalStack, set quality profile model as empty.")
            return

        # Check for material compatibility
        if not self._machine_manager.activeMaterialsCompatible():
            Logger.log("d", "No active material compatibility, set quality profile model as empty.")
            self.setItems([])
            return

        quality_group_dict = self._quality_manager.getQualityGroups(global_stack)

        item_list = []
        for key in sorted(quality_group_dict):
            quality_group = quality_group_dict[key]

            layer_height = self._fetchLayerHeight(quality_group)

            item = {"name": quality_group.name,
                    "quality_type": quality_group.quality_type,
                    "layer_height": layer_height,
                    "layer_height_unit": self._layer_height_unit,
                    "available": quality_group.is_available,
                    "quality_group": quality_group}

            item_list.append(item)

        # Sort items based on layer_height
        item_list = sorted(item_list, key = lambda x: x["layer_height"])

        self.setItems(item_list)

    def _fetchLayerHeight(self, quality_group: "QualityGroup") -> float:
        global_stack = self._machine_manager.activeMachine
        if not self._layer_height_unit:
            unit = global_stack.definition.getProperty("layer_height", "unit")
            if not unit:
                unit = ""
            self._layer_height_unit = unit

        default_layer_height = global_stack.definition.getProperty("layer_height", "value")

        # Get layer_height from the quality profile for the GlobalStack
        if quality_group.node_for_global is None:
            return float(default_layer_height)
        container = quality_group.node_for_global.getContainer()

        layer_height = default_layer_height
        if container and container.hasProperty("layer_height", "value"):
            layer_height = container.getProperty("layer_height", "value")
        else:
            # Look for layer_height in the GlobalStack from material -> definition
            container = global_stack.definition
            if container and container.hasProperty("layer_height", "value"):
                layer_height = container.getProperty("layer_height", "value")

        if isinstance(layer_height, SettingFunction):
            layer_height = layer_height(global_stack)

        return float(layer_height)
