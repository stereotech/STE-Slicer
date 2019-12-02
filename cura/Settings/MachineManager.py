# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import collections
import time
from typing import Any, Callable, List, Dict, TYPE_CHECKING, Optional, cast

from UM.ConfigurationErrorMessage import ConfigurationErrorMessage
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Settings.InstanceContainer import InstanceContainer
from UM.Settings.Interfaces import ContainerInterface
from UM.Signal import Signal

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, QTimer
from UM.FlameProfiler import pyqtSlot
from UM import Util
from UM.Logger import Logger
from UM.Message import Message

from UM.Settings.SettingFunction import SettingFunction
from UM.Signal import postponeSignals, CompressTechnique

from cura.Machines.QualityManager import getMachineDefinitionIDForQualitySearch
from cura.PrinterOutputDevice import PrinterOutputDevice
from cura.PrinterOutput.ConfigurationModel import ConfigurationModel
from cura.PrinterOutput.ExtruderConfigurationModel import ExtruderConfigurationModel
from cura.PrinterOutput.MaterialOutputModel import MaterialOutputModel
from cura.Settings.CuraContainerRegistry import CuraContainerRegistry
from cura.Settings.ExtruderManager import ExtruderManager
from cura.Settings.ExtruderStack import ExtruderStack
from cura.Settings.cura_empty_instance_containers import (empty_definition_changes_container, empty_variant_container,
                                                          empty_material_container, empty_quality_container,
                                                          empty_quality_changes_container)

from .CuraStackBuilder import CuraStackBuilder

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")

if TYPE_CHECKING:
    from cura.CuraApplication import CuraApplication
    from cura.Settings.CuraContainerStack import CuraContainerStack
    from cura.Settings.GlobalStack import GlobalStack
    from cura.Machines.MaterialManager import MaterialManager
    from cura.Machines.QualityManager import QualityManager
    from cura.Machines.VariantManager import VariantManager
    from cura.Machines.ContainerNode import ContainerNode
    from cura.Machines.QualityChangesGroup import QualityChangesGroup
    from cura.Machines.QualityGroup import QualityGroup


class MachineManager(QObject):
    def __init__(self, application: "CuraApplication", parent: Optional["QObject"] = None) -> None:
        super().__init__(parent)

        self._active_container_stack = None     # type: Optional[ExtruderStack]
        self._global_container_stack = None     # type: Optional[GlobalStack]

        self._current_root_material_id = {}  # type: Dict[str, str]
        self._current_quality_group = None   # type: Optional[QualityGroup]
        self._current_quality_changes_group = None  # type: Optional[QualityChangesGroup]

        self._default_extruder_position = "0"  # to be updated when extruders are switched on and off

        self.machine_extruder_material_update_dict = collections.defaultdict(list) #type: Dict[str, List[Callable[[], None]]]

        self._instance_container_timer = QTimer() #type: QTimer
        self._instance_container_timer.setInterval(250)
        self._instance_container_timer.setSingleShot(True)
        self._instance_container_timer.timeout.connect(self.__emitChangedSignals)

        self._application = application
        self._container_registry = self._application.getContainerRegistry()
        self._application.globalContainerStackChanged.connect(self._onGlobalContainerChanged)
        self._container_registry.containerLoadComplete.connect(self._onContainersChanged)

        ##  When the global container is changed, active material probably needs to be updated.
        self.globalContainerChanged.connect(self.activeMaterialChanged)
        self.globalContainerChanged.connect(self.activeVariantChanged)
        self.globalContainerChanged.connect(self.activeQualityChanged)

        self.globalContainerChanged.connect(self.activeQualityChangesGroupChanged)
        self.globalContainerChanged.connect(self.activeQualityGroupChanged)

        self._stacks_have_errors = None  # type: Optional[bool]

        self._onGlobalContainerChanged()

        ExtruderManager.getInstance().activeExtruderChanged.connect(self._onActiveExtruderStackChanged)
        self._onActiveExtruderStackChanged()

        ExtruderManager.getInstance().activeExtruderChanged.connect(self.activeMaterialChanged)
        ExtruderManager.getInstance().activeExtruderChanged.connect(self.activeVariantChanged)
        ExtruderManager.getInstance().activeExtruderChanged.connect(self.activeQualityChanged)

        self.globalContainerChanged.connect(self.activeStackChanged)
        self.globalValueChanged.connect(self.activeStackValueChanged)
        ExtruderManager.getInstance().activeExtruderChanged.connect(self.activeStackChanged)
        self.activeStackChanged.connect(self.activeStackValueChanged)

        self._application.getPreferences().addPreference("cura/active_machine", "")

        self._printer_output_devices = []  # type: List[PrinterOutputDevice]
        self._application.getOutputDeviceManager().outputDevicesChanged.connect(self._onOutputDevicesChanged)
        # There might already be some output devices by the time the signal is connected
        self._onOutputDevicesChanged()

        self._current_printer_configuration = ConfigurationModel()   # Indicates the current configuration setup in this printer
        self.activeMaterialChanged.connect(self._onCurrentConfigurationChanged)
        self.activeVariantChanged.connect(self._onCurrentConfigurationChanged)
        # Force to compute the current configuration
        self._onCurrentConfigurationChanged()

        self._application.callLater(self.setInitialActiveMachine)

        self._material_incompatible_message = Message(catalog.i18nc("@info:status",
                                                "The selected material is incompatible with the selected machine or configuration."),
                                                title = catalog.i18nc("@info:title", "Incompatible Material")) #type: Message

        containers = CuraContainerRegistry.getInstance().findInstanceContainers(id = self.activeMaterialId) #type: List[InstanceContainer]
        if containers:
            containers[0].nameChanged.connect(self._onMaterialNameChanged)

        self._material_manager = self._application.getMaterialManager() #type: MaterialManager
        self._variant_manager = self._application.getVariantManager() #type: VariantManager
        self._quality_manager = self._application.getQualityManager() #type: QualityManager

        # When the materials lookup table gets updated, it can mean that a material has its name changed, which should
        # be reflected on the GUI. This signal emission makes sure that it happens.
        self._material_manager.materialsUpdated.connect(self.rootMaterialChanged)
        # When the materials get updated, it can be that an activated material's diameter gets changed. In that case,
        # a material update should be triggered to make sure that the machine still has compatible materials activated.
        self._material_manager.materialsUpdated.connect(self._updateUponMaterialMetadataChange)
        self.rootMaterialChanged.connect(self._onRootMaterialChanged)

        # Emit the printerConnectedStatusChanged when either globalContainerChanged or outputDevicesChanged are emitted
        self.globalContainerChanged.connect(self.printerConnectedStatusChanged)
        self.outputDevicesChanged.connect(self.printerConnectedStatusChanged)

    activeQualityGroupChanged = pyqtSignal()
    activeQualityChangesGroupChanged = pyqtSignal()

    globalContainerChanged = pyqtSignal()  # Emitted whenever the global stack is changed (ie: when changing between printers, changing a global profile, but not when changing a value)
    activeMaterialChanged = pyqtSignal()
    activeVariantChanged = pyqtSignal()
    activeQualityChanged = pyqtSignal()
    activeStackChanged = pyqtSignal()  # Emitted whenever the active stack is changed (ie: when changing between extruders, changing a profile, but not when changing a value)
    extruderChanged = pyqtSignal()

    globalValueChanged = pyqtSignal()  # Emitted whenever a value inside global container is changed.
    activeStackValueChanged = pyqtSignal()  # Emitted whenever a value inside the active stack is changed.
    activeStackValidationChanged = pyqtSignal()  # Emitted whenever a validation inside active container is changed
    stacksValidationChanged = pyqtSignal()  # Emitted whenever a validation is changed
    numberExtrudersEnabledChanged = pyqtSignal()  # Emitted when the number of extruders that are enabled changed

    blurSettings = pyqtSignal()  # Emitted to force fields in the advanced sidebar to un-focus, so they update properly

    outputDevicesChanged = pyqtSignal()
    currentConfigurationChanged = pyqtSignal() # Emitted every time the current configurations of the machine changes
    printerConnectedStatusChanged = pyqtSignal() # Emitted every time the active machine change or the outputdevices change

    rootMaterialChanged = pyqtSignal()

    def setInitialActiveMachine(self) -> None:
        active_machine_id = self._application.getPreferences().getValue("cura/active_machine")
        if active_machine_id != "" and CuraContainerRegistry.getInstance().findContainerStacksMetadata(id = active_machine_id):
            # An active machine was saved, so restore it.
            self.setActiveMachine(active_machine_id)

    def _onOutputDevicesChanged(self) -> None:
        self._printer_output_devices = []
        for printer_output_device in self._application.getOutputDeviceManager().getOutputDevices():
            if isinstance(printer_output_device, PrinterOutputDevice):
                self._printer_output_devices.append(printer_output_device)

        self.outputDevicesChanged.emit()

    @pyqtProperty(QObject, notify = currentConfigurationChanged)
    def currentConfiguration(self) -> ConfigurationModel:
        return self._current_printer_configuration

    def _onCurrentConfigurationChanged(self) -> None:
        if not self._global_container_stack:
            return

        # Create the configuration model with the current data in Cura
        self._current_printer_configuration.printerType = self._global_container_stack.definition.getName()
        self._current_printer_configuration.extruderConfigurations = []
        for extruder in self._global_container_stack.extruders.values():
            extruder_configuration = ExtruderConfigurationModel()
            # For compare just the GUID is needed at this moment
            mat_type = extruder.material.getMetaDataEntry("material") if extruder.material != empty_material_container else None
            mat_guid = extruder.material.getMetaDataEntry("GUID") if extruder.material != empty_material_container else None
            mat_color = extruder.material.getMetaDataEntry("color_name") if extruder.material != empty_material_container else None
            mat_brand = extruder.material.getMetaDataEntry("brand") if extruder.material != empty_material_container else None
            mat_name = extruder.material.getMetaDataEntry("name") if extruder.material != empty_material_container else None
            material_model = MaterialOutputModel(mat_guid, mat_type, mat_color, mat_brand, mat_name)

            extruder_configuration.position = int(extruder.getMetaDataEntry("position"))
            extruder_configuration.material = material_model
            extruder_configuration.hotendID = extruder.variant.getName() if extruder.variant != empty_variant_container else None
            self._current_printer_configuration.extruderConfigurations.append(extruder_configuration)

        # an empty build plate configuration from the network printer is presented as an empty string, so use "" for an
        # empty build plate.
        self._current_printer_configuration.buildplateConfiguration = self._global_container_stack.getProperty("machine_buildplate_type", "value") if self._global_container_stack.variant != empty_variant_container else ""
        self.currentConfigurationChanged.emit()

    @pyqtSlot(QObject, result = bool)
    def matchesConfiguration(self, configuration: ConfigurationModel) -> bool:
        return self._current_printer_configuration == configuration

    @pyqtProperty("QVariantList", notify = outputDevicesChanged)
    def printerOutputDevices(self) -> List[PrinterOutputDevice]:
        return self._printer_output_devices

    @pyqtProperty(int, constant=True)
    def totalNumberOfSettings(self) -> int:
        general_definition_containers = CuraContainerRegistry.getInstance().findDefinitionContainers(id = "fdmprinter")
        if not general_definition_containers:
            return 0
        return len(general_definition_containers[0].getAllKeys())

    def _onGlobalContainerChanged(self) -> None:
        if self._global_container_stack:
            try:
                self._global_container_stack.nameChanged.disconnect(self._onMachineNameChanged)
            except TypeError:  # pyQtSignal gives a TypeError when disconnecting from something that was already disconnected.
                pass
            try:
                self._global_container_stack.containersChanged.disconnect(self._onContainersChanged)
            except TypeError:
                pass
            try:
                self._global_container_stack.propertyChanged.disconnect(self._onPropertyChanged)
            except TypeError:
                pass

            for extruder_stack in ExtruderManager.getInstance().getActiveExtruderStacks():
                extruder_stack.propertyChanged.disconnect(self._onPropertyChanged)
                extruder_stack.containersChanged.disconnect(self._onContainersChanged)

        # Update the local global container stack reference
        self._global_container_stack = self._application.getGlobalContainerStack()
        if self._global_container_stack:
            self.updateDefaultExtruder()
            self.updateNumberExtrudersEnabled()
        self.globalContainerChanged.emit()

        # after switching the global stack we reconnect all the signals and set the variant and material references
        if self._global_container_stack:
            self._application.getPreferences().setValue("cura/active_machine", self._global_container_stack.getId())

            self._global_container_stack.nameChanged.connect(self._onMachineNameChanged)
            self._global_container_stack.containersChanged.connect(self._onContainersChanged)
            self._global_container_stack.propertyChanged.connect(self._onPropertyChanged)

            # Global stack can have only a variant if it is a buildplate
            global_variant = self._global_container_stack.variant
            if global_variant != empty_variant_container:
                if global_variant.getMetaDataEntry("hardware_type") != "buildplate":
                    self._global_container_stack.setVariant(empty_variant_container)

            # set the global material to empty as we now use the extruder stack at all times - CURA-4482
            global_material = self._global_container_stack.material
            if global_material != empty_material_container:
                self._global_container_stack.setMaterial(empty_material_container)

            # Listen for changes on all extruder stacks
            for extruder_stack in ExtruderManager.getInstance().getActiveExtruderStacks():
                extruder_stack.propertyChanged.connect(self._onPropertyChanged)
                extruder_stack.containersChanged.connect(self._onContainersChanged)

            if self._global_container_stack.getId() in self.machine_extruder_material_update_dict:
                for func in self.machine_extruder_material_update_dict[self._global_container_stack.getId()]:
                    self._application.callLater(func)
                del self.machine_extruder_material_update_dict[self._global_container_stack.getId()]

        self.activeQualityGroupChanged.emit()

    def _onActiveExtruderStackChanged(self) -> None:
        self.blurSettings.emit()  # Ensure no-one has focus.
        old_active_container_stack = self._active_container_stack

        self._active_container_stack = ExtruderManager.getInstance().getActiveExtruderStack()

        if old_active_container_stack != self._active_container_stack:
            # Many methods and properties related to the active quality actually depend
            # on _active_container_stack. If it changes, then the properties change.
            self.activeQualityChanged.emit()

    def __emitChangedSignals(self) -> None:
        self.activeQualityChanged.emit()
        self.activeVariantChanged.emit()
        self.activeMaterialChanged.emit()

        self.rootMaterialChanged.emit()

    def _onContainersChanged(self, container: ContainerInterface) -> None:
        self._instance_container_timer.start()

    def _onPropertyChanged(self, key: str, property_name: str) -> None:
        if property_name == "value":
            # Notify UI items, such as the "changed" star in profile pull down menu.
            self.activeStackValueChanged.emit()

    ## Given a global_stack, make sure that it's all valid by searching for this quality group and applying it again
    def _initMachineState(self, global_stack: "CuraContainerStack") -> None:
        material_dict = {}
        for position, extruder in global_stack.extruders.items():
            material_dict[position] = extruder.material.getMetaDataEntry("base_file")
        self._current_root_material_id = material_dict

        # Update materials to make sure that the diameters match with the machine's
        for position in global_stack.extruders:
            self.updateMaterialWithVariant(position)

        global_quality = global_stack.quality
        quality_type = global_quality.getMetaDataEntry("quality_type")
        global_quality_changes = global_stack.qualityChanges
        global_quality_changes_name = global_quality_changes.getName()

        # Try to set the same quality/quality_changes as the machine specified.
        # If the quality/quality_changes is not available, switch to the default or the first quality that's available.
        same_quality_found = False
        quality_groups = self._application.getQualityManager().getQualityGroups(global_stack)

        if global_quality_changes.getId() != "empty_quality_changes":
            quality_changes_groups = self._application.getQualityManager().getQualityChangesGroups(global_stack)
            new_quality_changes_group = quality_changes_groups.get(global_quality_changes_name)
            if new_quality_changes_group is not None:
                self._setQualityChangesGroup(new_quality_changes_group)
                same_quality_found = True
                Logger.log("i", "Machine '%s' quality changes set to '%s'",
                           global_stack.getName(), new_quality_changes_group.name)
        else:
            new_quality_group = quality_groups.get(quality_type)
            if new_quality_group is not None:
                self._setQualityGroup(new_quality_group, empty_quality_changes = True)
                same_quality_found = True
                Logger.log("i", "Machine '%s' quality set to '%s'",
                           global_stack.getName(), new_quality_group.quality_type)

        # Could not find the specified quality/quality_changes, switch to the preferred quality if available,
        # otherwise the first quality that's available, otherwise empty (not supported).
        if not same_quality_found:
            Logger.log("i", "Machine '%s' could not find quality_type '%s' and quality_changes '%s'. "
                       "Available quality types are [%s]. Switching to default quality.",
                       global_stack.getName(), quality_type, global_quality_changes_name,
                       ", ".join(quality_groups.keys()))
            preferred_quality_type = global_stack.getMetaDataEntry("preferred_quality_type")
            quality_group = quality_groups.get(preferred_quality_type)
            if quality_group is None:
                if quality_groups:
                    quality_group = list(quality_groups.values())[0]
            self._setQualityGroup(quality_group, empty_quality_changes = True)

    @pyqtSlot(str)
    def setActiveMachine(self, stack_id: str) -> None:
        self.blurSettings.emit()  # Ensure no-one has focus.

        container_registry = CuraContainerRegistry.getInstance()

        containers = container_registry.findContainerStacks(id = stack_id)
        if not containers:
            return

        global_stack = containers[0]

        # Make sure that the default machine actions for this machine have been added
        self._application.getMachineActionManager().addDefaultMachineActions(global_stack)

        ExtruderManager.getInstance()._fixSingleExtrusionMachineExtruderDefinition(global_stack)
        if not global_stack.isValid():
            # Mark global stack as invalid
            ConfigurationErrorMessage.getInstance().addFaultyContainers(global_stack.getId())
            return  # We're done here
        ExtruderManager.getInstance().setActiveExtruderIndex(0)  # Switch to first extruder
        self._global_container_stack = global_stack
        self._application.setGlobalContainerStack(global_stack)
        ExtruderManager.getInstance()._globalContainerStackChanged()
        self._initMachineState(global_stack)
        self._onGlobalContainerChanged()

        self.__emitChangedSignals()

    ##  Given a definition id, return the machine with this id.
    #   Optional: add a list of keys and values to filter the list of machines with the given definition id
    #   \param definition_id \type{str} definition id that needs to look for
    #   \param metadata_filter \type{dict} list of metadata keys and values used for filtering
    @staticmethod
    def getMachine(definition_id: str, metadata_filter: Optional[Dict[str, str]] = None) -> Optional["GlobalStack"]:
        if metadata_filter is None:
            metadata_filter = {}
        machines = CuraContainerRegistry.getInstance().findContainerStacks(type = "machine", **metadata_filter)
        for machine in machines:
            if machine.definition.getId() == definition_id:
                return machine
        return None

    @pyqtSlot(str, str)
    def addMachine(self, name: str, definition_id: str) -> None:
        new_stack = CuraStackBuilder.createMachine(name, definition_id)
        if new_stack:
            # Instead of setting the global container stack here, we set the active machine and so the signals are emitted
            self.setActiveMachine(new_stack.getId())
        else:
            Logger.log("w", "Failed creating a new machine!")

    def _checkStacksHaveErrors(self) -> bool:
        time_start = time.time()
        if self._global_container_stack is None: #No active machine.
            return False

        if self._global_container_stack.hasErrors():
            Logger.log("d", "Checking global stack for errors took %0.2f s and we found an error" % (time.time() - time_start))
            return True

        # Not a very pretty solution, but the extruder manager doesn't really know how many extruders there are
        machine_extruder_count = self._global_container_stack.getProperty("machine_extruder_count", "value")
        extruder_stacks = ExtruderManager.getInstance().getActiveExtruderStacks()
        count = 1  # we start with the global stack
        for stack in extruder_stacks:
            md = stack.getMetaData()
            if "position" in md and int(md["position"]) >= machine_extruder_count:
                continue
            count += 1
            if stack.hasErrors():
                Logger.log("d", "Checking %s stacks for errors took %.2f s and we found an error in stack [%s]" % (count, time.time() - time_start, str(stack)))
                return True

        Logger.log("d", "Checking %s stacks for errors took %.2f s" % (count, time.time() - time_start))
        return False

    ##  Check if the global_container has instances in the user container
    @pyqtProperty(bool, notify = activeStackValueChanged)
    def hasUserSettings(self) -> bool:
        if not self._global_container_stack:
            return False

        if self._global_container_stack.getTop().findInstances():
            return True

        stacks = ExtruderManager.getInstance().getActiveExtruderStacks()
        for stack in stacks:
            if stack.getTop().findInstances():
                return True

        return False

    @pyqtProperty(int, notify = activeStackValueChanged)
    def numUserSettings(self) -> int:
        if not self._global_container_stack:
            return 0
        num_user_settings = 0
        num_user_settings += len(self._global_container_stack.getTop().findInstances())
        stacks = ExtruderManager.getInstance().getActiveExtruderStacks()
        for stack in stacks:
            num_user_settings += len(stack.getTop().findInstances())
        return num_user_settings

    ##  Delete a user setting from the global stack and all extruder stacks.
    #   \param key \type{str} the name of the key to delete
    @pyqtSlot(str)
    def clearUserSettingAllCurrentStacks(self, key: str) -> None:
        if not self._global_container_stack:
            return

        send_emits_containers = []

        top_container = self._global_container_stack.getTop()
        top_container.removeInstance(key, postpone_emit=True)
        send_emits_containers.append(top_container)

        linked = not self._global_container_stack.getProperty(key, "settable_per_extruder") or \
                      self._global_container_stack.getProperty(key, "limit_to_extruder") != "-1"

        if not linked:
            stack = ExtruderManager.getInstance().getActiveExtruderStack()
            stacks = [stack]
        else:
            stacks = ExtruderManager.getInstance().getActiveExtruderStacks()

        for stack in stacks:
            if stack is not None:
                container = stack.getTop()
                container.removeInstance(key, postpone_emit=True)
                send_emits_containers.append(container)

        for container in send_emits_containers:
            container.sendPostponedEmits()

    ##  Check if none of the stacks contain error states
    #   Note that the _stacks_have_errors is cached due to performance issues
    #   Calling _checkStack(s)ForErrors on every change is simply too expensive
    @pyqtProperty(bool, notify = stacksValidationChanged)
    def stacksHaveErrors(self) -> bool:
        return bool(self._stacks_have_errors)

    @pyqtProperty(str, notify = globalContainerChanged)
    def activeMachineDefinitionName(self) -> str:
        if self._global_container_stack:
            return self._global_container_stack.definition.getName()
        return ""

    @pyqtProperty(str, notify = globalContainerChanged)
    def activeMachineName(self) -> str:
        if self._global_container_stack:
            return self._global_container_stack.getName()
        return ""

    @pyqtProperty(str, notify = globalContainerChanged)
    def activeMachineId(self) -> str:
        if self._global_container_stack:
            return self._global_container_stack.getId()
        return ""

    @pyqtProperty(bool, notify = printerConnectedStatusChanged)
    def printerConnected(self):
        return bool(self._printer_output_devices)

    @pyqtProperty(str, notify = printerConnectedStatusChanged)
    def activeMachineNetworkKey(self) -> str:
        if self._global_container_stack:
            return self._global_container_stack.getMetaDataEntry("um_network_key", "")
        return ""

    @pyqtProperty(str, notify = printerConnectedStatusChanged)
    def activeMachineNetworkGroupName(self) -> str:
        if self._global_container_stack:
            return self._global_container_stack.getMetaDataEntry("connect_group_name", "")
        return ""

    @pyqtProperty(QObject, notify = globalContainerChanged)
    def activeMachine(self) -> Optional["GlobalStack"]:
        return self._global_container_stack

    @pyqtProperty(str, notify = activeStackChanged)
    def activeStackId(self) -> str:
        if self._active_container_stack:
            return self._active_container_stack.getId()
        return ""

    @pyqtProperty(QObject, notify = activeStackChanged)
    def activeStack(self) -> Optional["ExtruderStack"]:
        return self._active_container_stack

    @pyqtProperty(str, notify=activeMaterialChanged)
    def activeMaterialId(self) -> str:
        if self._active_container_stack:
            material = self._active_container_stack.material
            if material:
                return material.getId()
        return ""

    ##  Gets a dict with the active materials ids set in all extruder stacks and the global stack
    #   (when there is one extruder, the material is set in the global stack)
    #
    #   \return The material ids in all stacks
    @pyqtProperty("QVariantMap", notify = activeMaterialChanged)
    def allActiveMaterialIds(self) -> Dict[str, str]:
        result = {}

        active_stacks = ExtruderManager.getInstance().getActiveExtruderStacks()
        for stack in active_stacks:
            material_container = stack.material
            if not material_container:
                continue
            result[stack.getId()] = material_container.getId()

        return result

    ##  Gets the layer height of the currently active quality profile.
    #
    #   This is indicated together with the name of the active quality profile.
    #
    #   \return The layer height of the currently active quality profile. If
    #   there is no quality profile, this returns 0.
    @pyqtProperty(float, notify = activeQualityGroupChanged)
    def activeQualityLayerHeight(self) -> float:
        if not self._global_container_stack:
            return 0
        if self._current_quality_changes_group:
            value = self._global_container_stack.getRawProperty("layer_height", "value", skip_until_container = self._global_container_stack.qualityChanges.getId())
            if isinstance(value, SettingFunction):
                value = value(self._global_container_stack)
            return value
        elif self._current_quality_group:
            value = self._global_container_stack.getRawProperty("layer_height", "value", skip_until_container = self._global_container_stack.quality.getId())
            if isinstance(value, SettingFunction):
                value = value(self._global_container_stack)
            return value
        return 0

    @pyqtProperty(str, notify = activeVariantChanged)
    def globalVariantName(self) -> str:
        if self._global_container_stack:
            variant = self._global_container_stack.variant
            if variant and not isinstance(variant, type(empty_variant_container)):
                return variant.getName()
        return ""

    @pyqtProperty(str, notify = activeQualityGroupChanged)
    def activeQualityType(self) -> str:
        quality_type = ""
        if self._active_container_stack:
            if self._current_quality_group:
                quality_type = self._current_quality_group.quality_type
        return quality_type

    @pyqtProperty(bool, notify = activeQualityGroupChanged)
    def isActiveQualitySupported(self) -> bool:
        is_supported = False
        if self._global_container_stack:
            if self._current_quality_group:
                is_supported = self._current_quality_group.is_available
        return is_supported

    ##  Returns whether there is anything unsupported in the current set-up.
    #
    #   The current set-up signifies the global stack and all extruder stacks,
    #   so this indicates whether there is any container in any of the container
    #   stacks that is not marked as supported.
    @pyqtProperty(bool, notify = activeQualityChanged)
    def isCurrentSetupSupported(self) -> bool:
        if not self._global_container_stack:
            return False
        for stack in [self._global_container_stack] + list(self._global_container_stack.extruders.values()):
            for container in stack.getContainers():
                if not container:
                    return False
                if not Util.parseBool(container.getMetaDataEntry("supported", True)):
                    return False
        return True

    ## Check if a container is read_only
    @pyqtSlot(str, result = bool)
    def isReadOnly(self, container_id: str) -> bool:
        return CuraContainerRegistry.getInstance().isReadOnly(container_id)

    ## Copy the value of the setting of the current extruder to all other extruders as well as the global container.
    @pyqtSlot(str)
    def copyValueToExtruders(self, key: str) -> None:
        if self._active_container_stack is None or self._global_container_stack is None:
            return
        new_value = self._active_container_stack.getProperty(key, "value")
        extruder_stacks = [stack for stack in ExtruderManager.getInstance().getActiveExtruderStacks()]

        # check in which stack the value has to be replaced
        for extruder_stack in extruder_stacks:
            if extruder_stack != self._active_container_stack and extruder_stack.getProperty(key, "value") != new_value:
                extruder_stack.userChanges.setProperty(key, "value", new_value)  # TODO: nested property access, should be improved

    ## Copy the value of all manually changed settings of the current extruder to all other extruders.
    @pyqtSlot()
    def copyAllValuesToExtruders(self) -> None:
        if self._active_container_stack is None or self._global_container_stack is None:
            return
        extruder_stacks = list(self._global_container_stack.extruders.values())
        for extruder_stack in extruder_stacks:
            if extruder_stack != self._active_container_stack:
                for key in self._active_container_stack.userChanges.getAllKeys():
                    new_value = self._active_container_stack.getProperty(key, "value")

                    # check if the value has to be replaced
                    extruder_stack.userChanges.setProperty(key, "value", new_value)

    @pyqtProperty(str, notify = activeVariantChanged)
    def activeVariantName(self) -> str:
        if self._active_container_stack:
            variant = self._active_container_stack.variant
            if variant:
                return variant.getName()

        return ""

    @pyqtProperty(str, notify = activeVariantChanged)
    def activeVariantId(self) -> str:
        if self._active_container_stack:
            variant = self._active_container_stack.variant
            if variant:
                return variant.getId()

        return ""

    @pyqtProperty(str, notify = activeVariantChanged)
    def activeVariantBuildplateName(self) -> str:
        if self._global_container_stack:
            variant = self._global_container_stack.variant
            if variant:
                return variant.getName()

        return ""

    @pyqtProperty(str, notify = globalContainerChanged)
    def activeDefinitionId(self) -> str:
        if self._global_container_stack:
            return self._global_container_stack.definition.id

        return ""

    ##  Get the Definition ID to use to select quality profiles for the currently active machine
    #   \returns DefinitionID (string) if found, empty string otherwise
    @pyqtProperty(str, notify = globalContainerChanged)
    def activeQualityDefinitionId(self) -> str:
        if self._global_container_stack:
            return getMachineDefinitionIDForQualitySearch(self._global_container_stack.definition)
        return ""

    ##  Gets how the active definition calls variants
    #   Caveat: per-definition-variant-title is currently not translated (though the fallback is)
    @pyqtProperty(str, notify = globalContainerChanged)
    def activeDefinitionVariantsName(self) -> str:
        fallback_title = catalog.i18nc("@label", "Nozzle")
        if self._global_container_stack:
            return self._global_container_stack.definition.getMetaDataEntry("variants_name", fallback_title)

        return fallback_title

    @pyqtSlot(str, str)
    def renameMachine(self, machine_id: str, new_name: str) -> None:
        container_registry = CuraContainerRegistry.getInstance()
        machine_stack = container_registry.findContainerStacks(id = machine_id)
        if machine_stack:
            new_name = container_registry.createUniqueName("machine", machine_stack[0].getName(), new_name, machine_stack[0].definition.getName())
            machine_stack[0].setName(new_name)
            self.globalContainerChanged.emit()

    @pyqtSlot(str)
    def removeMachine(self, machine_id: str) -> None:
        # If the machine that is being removed is the currently active machine, set another machine as the active machine.
        activate_new_machine = (self._global_container_stack and self._global_container_stack.getId() == machine_id)

        # activate a new machine before removing a machine because this is safer
        if activate_new_machine:
            machine_stacks = CuraContainerRegistry.getInstance().findContainerStacksMetadata(type = "machine")
            other_machine_stacks = [s for s in machine_stacks if s["id"] != machine_id]
            if other_machine_stacks:
                self.setActiveMachine(other_machine_stacks[0]["id"])

        metadata = CuraContainerRegistry.getInstance().findContainerStacksMetadata(id = machine_id)[0]
        network_key = metadata["um_network_key"] if "um_network_key" in metadata else None
        ExtruderManager.getInstance().removeMachineExtruders(machine_id)
        containers = CuraContainerRegistry.getInstance().findInstanceContainersMetadata(type = "user", machine = machine_id)
        for container in containers:
            CuraContainerRegistry.getInstance().removeContainer(container["id"])
        CuraContainerRegistry.getInstance().removeContainer(machine_id)

        # If the printer that is being removed is a network printer, the hidden printers have to be also removed
        if network_key:
            metadata_filter = {"um_network_key": network_key}
            hidden_containers = CuraContainerRegistry.getInstance().findContainerStacks(type = "machine", **metadata_filter)
            if hidden_containers:
                # This reuses the method and remove all printers recursively
                self.removeMachine(hidden_containers[0].getId())

    @pyqtProperty(bool, notify = globalContainerChanged)
    def hasMaterials(self) -> bool:
        if self._global_container_stack:
            return Util.parseBool(self._global_container_stack.getMetaDataEntry("has_materials", False))
        return False

    @pyqtProperty(bool, notify = globalContainerChanged)
    def hasVariants(self) -> bool:
        if self._global_container_stack:
            return Util.parseBool(self._global_container_stack.getMetaDataEntry("has_variants", False))
        return False

    @pyqtProperty(bool, notify = globalContainerChanged)
    def hasVariantBuildplates(self) -> bool:
        if self._global_container_stack:
            return Util.parseBool(self._global_container_stack.getMetaDataEntry("has_variant_buildplates", False))
        return False

    ##  The selected buildplate is compatible if it is compatible with all the materials in all the extruders
    @pyqtProperty(bool, notify = activeMaterialChanged)
    def variantBuildplateCompatible(self) -> bool:
        if not self._global_container_stack:
            return True

        buildplate_compatible = True  # It is compatible by default
        extruder_stacks = self._global_container_stack.extruders.values()
        for stack in extruder_stacks:
            if not stack.isEnabled:
                continue
            material_container = stack.material
            if material_container == empty_material_container:
                continue
            if material_container.getMetaDataEntry("buildplate_compatible"):
                buildplate_compatible = buildplate_compatible and material_container.getMetaDataEntry("buildplate_compatible")[self.activeVariantBuildplateName]

        return buildplate_compatible

    ##  The selected buildplate is usable if it is usable for all materials OR it is compatible for one but not compatible
    #   for the other material but the buildplate is still usable
    @pyqtProperty(bool, notify = activeMaterialChanged)
    def variantBuildplateUsable(self) -> bool:
        if not self._global_container_stack:
            return True

        # Here the next formula is being calculated:
        # result = (not (material_left_compatible and material_right_compatible)) and
        #           (material_left_compatible or material_left_usable) and
        #           (material_right_compatible or material_right_usable)
        result = not self.variantBuildplateCompatible
        extruder_stacks = self._global_container_stack.extruders.values()
        for stack in extruder_stacks:
            material_container = stack.material
            if material_container == empty_material_container:
                continue
            buildplate_compatible = material_container.getMetaDataEntry("buildplate_compatible")[self.activeVariantBuildplateName] if material_container.getMetaDataEntry("buildplate_compatible") else True
            buildplate_usable = material_container.getMetaDataEntry("buildplate_recommended")[self.activeVariantBuildplateName] if material_container.getMetaDataEntry("buildplate_recommended") else True

            result = result and (buildplate_compatible or buildplate_usable)

        return result

    ##  Get the Definition ID of a machine (specified by ID)
    #   \param machine_id string machine id to get the definition ID of
    #   \returns DefinitionID if found, None otherwise
    @pyqtSlot(str, result = str)
    def getDefinitionByMachineId(self, machine_id: str) -> Optional[str]:
        containers = CuraContainerRegistry.getInstance().findContainerStacks(id = machine_id)
        if containers:
            return containers[0].definition.getId()
        return None

    def getIncompatibleSettingsOnEnabledExtruders(self, container: InstanceContainer) -> List[str]:
        if self._global_container_stack is None:
            return []
        extruder_count = self._global_container_stack.getProperty("machine_extruder_count", "value")
        result = []  # type: List[str]
        for setting_instance in container.findInstances():
            setting_key = setting_instance.definition.key
            setting_enabled = self._global_container_stack.getProperty(setting_key, "enabled")
            if not setting_enabled:
                # A setting is not visible anymore
                result.append(setting_key)
                Logger.log("d", "Reset setting [%s] from [%s] because the setting is no longer enabled", setting_key, container)
                continue

            if not self._global_container_stack.getProperty(setting_key, "type") in ("extruder", "optional_extruder"):
                continue

            old_value = container.getProperty(setting_key, "value")
            if int(old_value) < 0:
                continue
            if int(old_value) >= extruder_count or not self._global_container_stack.extruders[str(old_value)].isEnabled:
                result.append(setting_key)
                Logger.log("d", "Reset setting [%s] in [%s] because its old value [%s] is no longer valid", setting_key, container, old_value)
        return result

    ##  Update extruder number to a valid value when the number of extruders are changed, or when an extruder is changed
    def correctExtruderSettings(self) -> None:
        if self._global_container_stack is None:
            return
        for setting_key in self.getIncompatibleSettingsOnEnabledExtruders(self._global_container_stack.userChanges):
            self._global_container_stack.userChanges.removeInstance(setting_key)
        add_user_changes = self.getIncompatibleSettingsOnEnabledExtruders(self._global_container_stack.qualityChanges)
        for setting_key in add_user_changes:
            # Apply quality changes that are incompatible to user changes, so we do not change the quality changes itself.
            self._global_container_stack.userChanges.setProperty(setting_key, "value", self._default_extruder_position)
        if add_user_changes:
            caution_message = Message(catalog.i18nc(
                "@info:generic",
                "Settings have been changed to match the current availability of extruders: [%s]" % ", ".join(add_user_changes)),
                lifetime=0,
                title = catalog.i18nc("@info:title", "Settings updated"))
            caution_message.show()

    ##  Set the amount of extruders on the active machine (global stack)
    #   \param extruder_count int the number of extruders to set
    def setActiveMachineExtruderCount(self, extruder_count: int) -> None:
        if self._global_container_stack is None:
            return
        extruder_manager = self._application.getExtruderManager()

        definition_changes_container = self._global_container_stack.definitionChanges
        if not self._global_container_stack or definition_changes_container == empty_definition_changes_container:
            return

        previous_extruder_count = self._global_container_stack.getProperty("machine_extruder_count", "value")
        if extruder_count == previous_extruder_count:
            return

        definition_changes_container.setProperty("machine_extruder_count", "value", extruder_count)

        self.updateDefaultExtruder()
        self.updateNumberExtrudersEnabled()
        self.correctExtruderSettings()

        # Check to see if any objects are set to print with an extruder that will no longer exist
        root_node = self._application.getController().getScene().getRoot()
        for node in DepthFirstIterator(root_node): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            if node.getMeshData():
                extruder_nr = node.callDecoration("getActiveExtruderPosition")

                if extruder_nr is not None and int(extruder_nr) > extruder_count - 1:
                    extruder = extruder_manager.getExtruderStack(extruder_count - 1)
                    if extruder is not None:
                        node.callDecoration("setActiveExtruder", extruder.getId())
                    else:
                        Logger.log("w", "Could not find extruder to set active.")

        # Make sure one of the extruder stacks is active
        extruder_manager.setActiveExtruderIndex(0)

        # Move settable_per_extruder values out of the global container
        # After CURA-4482 this should not be the case anymore, but we still want to support older project files.
        global_user_container = self._global_container_stack.userChanges

        # Make sure extruder_stacks exists
        extruder_stacks = [] #type: List[ExtruderStack]

        if previous_extruder_count == 1:
            extruder_stacks = ExtruderManager.getInstance().getActiveExtruderStacks()
            global_user_container = self._global_container_stack.userChanges

        for setting_instance in global_user_container.findInstances():
            setting_key = setting_instance.definition.key
            settable_per_extruder = self._global_container_stack.getProperty(setting_key, "settable_per_extruder")

            if settable_per_extruder:
                limit_to_extruder = int(self._global_container_stack.getProperty(setting_key, "limit_to_extruder"))
                extruder_stack = extruder_stacks[max(0, limit_to_extruder)]
                extruder_stack.userChanges.setProperty(setting_key, "value", global_user_container.getProperty(setting_key, "value"))
                global_user_container.removeInstance(setting_key)

        # Signal that the global stack has changed
        self._application.globalContainerStackChanged.emit()
        self.forceUpdateAllSettings()

    @pyqtSlot(int, result = QObject)
    def getExtruder(self, position: int) -> Optional[ExtruderStack]:
        extruder = None
        if self._global_container_stack:
            extruder = self._global_container_stack.extruders.get(str(position))
        return extruder

    def updateDefaultExtruder(self) -> None:
        if self._global_container_stack is None:
            return
        extruder_items = sorted(self._global_container_stack.extruders.items())
        old_position = self._default_extruder_position
        new_default_position = "0"
        for position, extruder in extruder_items:
            if extruder.isEnabled:
                new_default_position = position
                break
        if new_default_position != old_position:
            self._default_extruder_position = new_default_position
            self.extruderChanged.emit()

    def updateNumberExtrudersEnabled(self) -> None:
        if self._global_container_stack is None:
            return
        definition_changes_container = self._global_container_stack.definitionChanges
        machine_extruder_count = self._global_container_stack.getProperty("machine_extruder_count", "value")
        extruder_count = 0
        for position, extruder in self._global_container_stack.extruders.items():
            if extruder.isEnabled and int(position) < machine_extruder_count:
                extruder_count += 1
        if self.numberExtrudersEnabled != extruder_count:
            definition_changes_container.setProperty("extruders_enabled_count", "value", extruder_count)
            self.numberExtrudersEnabledChanged.emit()

    @pyqtProperty(int, notify = numberExtrudersEnabledChanged)
    def numberExtrudersEnabled(self) -> int:
        if self._global_container_stack is None:
            return 1
        return self._global_container_stack.definitionChanges.getProperty("extruders_enabled_count", "value")

    @pyqtProperty(str, notify = extruderChanged)
    def defaultExtruderPosition(self) -> str:
        return self._default_extruder_position

    ##  This will fire the propertiesChanged for all settings so they will be updated in the front-end
    @pyqtSlot()
    def forceUpdateAllSettings(self) -> None:
        if self._global_container_stack is None:
            return
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            property_names = ["value", "resolve", "validationState"]
            for container in [self._global_container_stack] + list(self._global_container_stack.extruders.values()):
                for setting_key in container.getAllKeys():
                    container.propertiesChanged.emit(setting_key, property_names)

    @pyqtSlot(int, bool)
    def setExtruderEnabled(self, position: int, enabled: bool) -> None:
        extruder = self.getExtruder(position)
        if not extruder or self._global_container_stack is None:
            Logger.log("w", "Could not find extruder on position %s", position)
            return

        extruder.setEnabled(enabled)
        self.updateDefaultExtruder()
        self.updateNumberExtrudersEnabled()
        self.correctExtruderSettings()

        # In case this extruder is being disabled and it's the currently selected one, switch to the default extruder
        if not enabled and position == ExtruderManager.getInstance().activeExtruderIndex:
            ExtruderManager.getInstance().setActiveExtruderIndex(int(self._default_extruder_position))

        # ensure that the quality profile is compatible with current combination, or choose a compatible one if available
        self._updateQualityWithMaterial()
        self.extruderChanged.emit()
        # update material compatibility color
        self.activeQualityGroupChanged.emit()
        # update items in SettingExtruder
        ExtruderManager.getInstance().extrudersChanged.emit(self._global_container_stack.getId())
        # Make sure the front end reflects changes
        self.forceUpdateAllSettings()
        # Also trigger the build plate compatibility to update
        self.activeMaterialChanged.emit()

    def _onMachineNameChanged(self) -> None:
        self.globalContainerChanged.emit()

    def _onMaterialNameChanged(self) -> None:
        self.activeMaterialChanged.emit()

    def _onQualityNameChanged(self) -> None:
        self.activeQualityChanged.emit()

    def _getContainerChangedSignals(self) -> List[Signal]:
        if self._global_container_stack is None:
            return []
        stacks = ExtruderManager.getInstance().getActiveExtruderStacks()
        stacks.append(self._global_container_stack)
        return [ s.containersChanged for s in stacks ]

    @pyqtSlot(str, str, str)
    def setSettingForAllExtruders(self, setting_name: str, property_name: str, property_value: str) -> None:
        if self._global_container_stack is None:
            return
        for key, extruder in self._global_container_stack.extruders.items():
            container = extruder.userChanges
            container.setProperty(setting_name, property_name, property_value)

    ##  Reset all setting properties of a setting for all extruders.
    #   \param setting_name The ID of the setting to reset.
    @pyqtSlot(str)
    def resetSettingForAllExtruders(self, setting_name: str) -> None:
        if self._global_container_stack is None:
            return
        for key, extruder in self._global_container_stack.extruders.items():
            container = extruder.userChanges
            container.removeInstance(setting_name)

    @pyqtProperty("QVariantList", notify = globalContainerChanged)
    def currentExtruderPositions(self) -> List[str]:
        if self._global_container_stack is None:
            return []
        return sorted(list(self._global_container_stack.extruders.keys()))

    ##  Update _current_root_material_id when the current root material was changed.
    def _onRootMaterialChanged(self) -> None:
        self._current_root_material_id = {}

        if self._global_container_stack:
            for position in self._global_container_stack.extruders:
                self._current_root_material_id[position] = self._global_container_stack.extruders[position].material.getMetaDataEntry("base_file")

    @pyqtProperty("QVariant", notify = rootMaterialChanged)
    def currentRootMaterialId(self) -> Dict[str, str]:
        return self._current_root_material_id

    ##  Return the variant names in the extruder stack(s).
    ##  For the variant in the global stack, use activeVariantBuildplateName
    @pyqtProperty("QVariant", notify = activeVariantChanged)
    def activeVariantNames(self) -> Dict[str, str]:
        result = {}

        active_stacks = ExtruderManager.getInstance().getActiveExtruderStacks()
        for stack in active_stacks:
            variant_container = stack.variant
            position = stack.getMetaDataEntry("position")
            if variant_container and variant_container != empty_variant_container:
                result[position] = variant_container.getName()

        return result

    #
    # Sets all quality and quality_changes containers to empty_quality and empty_quality_changes containers
    # for all stacks in the currently active machine.
    #
    def _setEmptyQuality(self) -> None:
        if self._global_container_stack is None:
            return
        self._current_quality_group = None
        self._current_quality_changes_group = None
        self._global_container_stack.quality = empty_quality_container
        self._global_container_stack.qualityChanges = empty_quality_changes_container
        for extruder in self._global_container_stack.extruders.values():
            extruder.quality = empty_quality_container
            extruder.qualityChanges = empty_quality_changes_container

        self.activeQualityGroupChanged.emit()
        self.activeQualityChangesGroupChanged.emit()

    def _setQualityGroup(self, quality_group: Optional["QualityGroup"], empty_quality_changes: bool = True) -> None:
        if self._global_container_stack is None:
            return
        if quality_group is None:
            self._setEmptyQuality()
            return

        if quality_group.node_for_global is None or quality_group.node_for_global.getContainer() is None:
            return
        for node in quality_group.nodes_for_extruders.values():
            if node.getContainer() is None:
                return

        self._current_quality_group = quality_group
        if empty_quality_changes:
            self._current_quality_changes_group = None

        # Set quality and quality_changes for the GlobalStack
        self._global_container_stack.quality = quality_group.node_for_global.getContainer()
        if empty_quality_changes:
            self._global_container_stack.qualityChanges = empty_quality_changes_container

        # Set quality and quality_changes for each ExtruderStack
        for position, node in quality_group.nodes_for_extruders.items():
            self._global_container_stack.extruders[str(position)].quality = node.getContainer()
            if empty_quality_changes:
                self._global_container_stack.extruders[str(position)].qualityChanges = empty_quality_changes_container

        self.activeQualityGroupChanged.emit()
        self.activeQualityChangesGroupChanged.emit()

    def _fixQualityChangesGroupToNotSupported(self, quality_changes_group: "QualityChangesGroup") -> None:
        nodes = [quality_changes_group.node_for_global] + list(quality_changes_group.nodes_for_extruders.values())
        containers = [n.getContainer() for n in nodes if n is not None]
        for container in containers:
            if container:
                container.setMetaDataEntry("quality_type", "not_supported")
        quality_changes_group.quality_type = "not_supported"

    def _setQualityChangesGroup(self, quality_changes_group: "QualityChangesGroup") -> None:
        if self._global_container_stack is None:
            return #Can't change that.
        quality_type = quality_changes_group.quality_type
        # A custom quality can be created based on "not supported".
        # In that case, do not set quality containers to empty.
        quality_group = None
        if quality_type != "not_supported":
            quality_group_dict = self._quality_manager.getQualityGroups(self._global_container_stack)
            quality_group = quality_group_dict.get(quality_type)
            if quality_group is None:
                self._fixQualityChangesGroupToNotSupported(quality_changes_group)

        quality_changes_container = empty_quality_changes_container
        quality_container = empty_quality_container  # type: Optional[InstanceContainer]
        if quality_changes_group.node_for_global and quality_changes_group.node_for_global.getContainer():
            quality_changes_container = cast(InstanceContainer, quality_changes_group.node_for_global.getContainer())
        if quality_group is not None and quality_group.node_for_global and quality_group.node_for_global.getContainer():
            quality_container = quality_group.node_for_global.getContainer()

        self._global_container_stack.quality = quality_container
        self._global_container_stack.qualityChanges = quality_changes_container

        for position, extruder in self._global_container_stack.extruders.items():
            quality_changes_node = quality_changes_group.nodes_for_extruders.get(position)
            quality_node = None
            if quality_group is not None:
                quality_node = quality_group.nodes_for_extruders.get(position)

            quality_changes_container = empty_quality_changes_container
            quality_container = empty_quality_container
            if quality_changes_node and quality_changes_node.getContainer():
                quality_changes_container = cast(InstanceContainer, quality_changes_node.getContainer())
            if quality_node and quality_node.getContainer():
                quality_container = quality_node.getContainer()

            extruder.quality = quality_container
            extruder.qualityChanges = quality_changes_container

        self._current_quality_group = quality_group
        self._current_quality_changes_group = quality_changes_group
        self.activeQualityGroupChanged.emit()
        self.activeQualityChangesGroupChanged.emit()

    def _setVariantNode(self, position: str, container_node: "ContainerNode") -> None:
        if container_node.getContainer() is None or self._global_container_stack is None:
            return
        self._global_container_stack.extruders[position].variant = container_node.getContainer()
        self.activeVariantChanged.emit()

    def _setGlobalVariant(self, container_node: "ContainerNode") -> None:
        if self._global_container_stack is None:
            return
        self._global_container_stack.variant = container_node.getContainer()
        if not self._global_container_stack.variant:
            self._global_container_stack.variant = self._application.empty_variant_container

    def _setMaterial(self, position: str, container_node: Optional["ContainerNode"] = None) -> None:
        if self._global_container_stack is None:
            return
        if container_node and container_node.getContainer():
            self._global_container_stack.extruders[position].material = container_node.getContainer()
            root_material_id = container_node.getMetaDataEntry("base_file", None)
        else:
            self._global_container_stack.extruders[position].material = empty_material_container
            root_material_id = None
        # The _current_root_material_id is used in the MaterialMenu to see which material is selected
        if root_material_id != self._current_root_material_id[position]:
            self._current_root_material_id[position] = root_material_id
            self.rootMaterialChanged.emit()

    def activeMaterialsCompatible(self) -> bool:
        # check material - variant compatibility
        if self._global_container_stack is not None:
            if Util.parseBool(self._global_container_stack.getMetaDataEntry("has_materials", False)):
                for position, extruder in self._global_container_stack.extruders.items():
                    if extruder.isEnabled and not extruder.material.getMetaDataEntry("compatible"):
                        return False
                    if not extruder.material.getMetaDataEntry("compatible"):
                        return False
        return True

    ## Update current quality type and machine after setting material
    def _updateQualityWithMaterial(self, *args: Any) -> None:
        if self._global_container_stack is None:
            return
        Logger.log("i", "Updating quality/quality_changes due to material change")
        current_quality_type = None
        if self._current_quality_group:
            current_quality_type = self._current_quality_group.quality_type
        candidate_quality_groups = self._quality_manager.getQualityGroups(self._global_container_stack)
        available_quality_types = {qt for qt, g in candidate_quality_groups.items() if g.is_available}

        Logger.log("d", "Current quality type = [%s]", current_quality_type)
        if not self.activeMaterialsCompatible():
            if current_quality_type is not None:
                Logger.log("i", "Active materials are not compatible, setting all qualities to empty (Not Supported).")
                self._setEmptyQuality()
            return

        if not available_quality_types:
            if self._current_quality_changes_group is None:
                Logger.log("i", "No available quality types found, setting all qualities to empty (Not Supported).")
                self._setEmptyQuality()
            return

        if current_quality_type in available_quality_types:
            Logger.log("i", "Current available quality type [%s] is available, applying changes.", current_quality_type)
            self._setQualityGroup(candidate_quality_groups[current_quality_type], empty_quality_changes = False)
            return

        # The current quality type is not available so we use the preferred quality type if it's available,
        # otherwise use one of the available quality types.
        quality_type = sorted(list(available_quality_types))[0]
        preferred_quality_type = self._global_container_stack.getMetaDataEntry("preferred_quality_type")
        if preferred_quality_type in available_quality_types:
            quality_type = preferred_quality_type

        Logger.log("i", "The current quality type [%s] is not available, switching to [%s] instead",
                   current_quality_type, quality_type)
        self._setQualityGroup(candidate_quality_groups[quality_type], empty_quality_changes = True)

    def updateMaterialWithVariant(self, position: Optional[str]) -> None:
        if self._global_container_stack is None:
            return
        if position is None:
            position_list = list(self._global_container_stack.extruders.keys())
        else:
            position_list = [position]

        buildplate_name = None
        if self._global_container_stack.variant.getId() != "empty_variant":
            buildplate_name = self._global_container_stack.variant.getName()

        for position_item in position_list:
            extruder = self._global_container_stack.extruders[position_item]

            current_material_base_name = extruder.material.getMetaDataEntry("base_file")
            current_nozzle_name = None
            if extruder.variant.getId() != empty_variant_container.getId():
                current_nozzle_name = extruder.variant.getMetaDataEntry("name")

            material_diameter = extruder.getCompatibleMaterialDiameter()
            candidate_materials = self._material_manager.getAvailableMaterials(
                self._global_container_stack.definition,
                current_nozzle_name,
                buildplate_name,
                material_diameter)

            if not candidate_materials:
                self._setMaterial(position_item, container_node = None)
                continue

            if current_material_base_name in candidate_materials:
                new_material = candidate_materials[current_material_base_name]
                self._setMaterial(position_item, new_material)
                continue

            # The current material is not available, find the preferred one
            material_node = self._material_manager.getDefaultMaterial(self._global_container_stack, position_item, current_nozzle_name)
            if material_node is not None:
                self._setMaterial(position_item, material_node)

    ##  Given a printer definition name, select the right machine instance. In case it doesn't exist, create a new
    #   instance with the same network key.
    @pyqtSlot(str)
    def switchPrinterType(self, machine_name: str) -> None:
        # Don't switch if the user tries to change to the same type of printer
        if self._global_container_stack is None or self.activeMachineDefinitionName == machine_name:
            return
        # Get the definition id corresponding to this machine name
        machine_definition_id = CuraContainerRegistry.getInstance().findDefinitionContainers(name = machine_name)[0].getId()
        # Try to find a machine with the same network key
        new_machine = self.getMachine(machine_definition_id, metadata_filter = {"um_network_key": self.activeMachineNetworkKey})
        # If there is no machine, then create a new one and set it to the non-hidden instance
        if not new_machine:
            new_machine = CuraStackBuilder.createMachine(machine_definition_id + "_sync", machine_definition_id)
            if not new_machine:
                return
            new_machine.setMetaDataEntry("um_network_key", self.activeMachineNetworkKey)
            new_machine.setMetaDataEntry("connect_group_name", self.activeMachineNetworkGroupName)
            new_machine.setMetaDataEntry("hidden", False)
        else:
            Logger.log("i", "Found a %s with the key %s. Let's use it!", machine_name, self.activeMachineNetworkKey)
            new_machine.setMetaDataEntry("hidden", False)

        # Set the current printer instance to hidden (the metadata entry must exist)
        self._global_container_stack.setMetaDataEntry("hidden", True)

        self.setActiveMachine(new_machine.getId())

    @pyqtSlot(QObject)
    def applyRemoteConfiguration(self, configuration: ConfigurationModel) -> None:
        if self._global_container_stack is None:
            return
        self.blurSettings.emit()
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self.switchPrinterType(configuration.printerType)
            for extruder_configuration in configuration.extruderConfigurations:
                position = str(extruder_configuration.position)
                variant_container_node = self._variant_manager.getVariantNode(self._global_container_stack.definition.getId(), extruder_configuration.hotendID)
                material_container_node = self._material_manager.getMaterialNodeByType(self._global_container_stack,
                                                                                       position,
                                                                                       extruder_configuration.hotendID,
                                                                                       configuration.buildplateConfiguration,
                                                                                       extruder_configuration.material.guid)

                if variant_container_node:
                    self._setVariantNode(position, variant_container_node)
                else:
                    self._global_container_stack.extruders[position].variant = empty_variant_container

                if material_container_node:
                    self._setMaterial(position, material_container_node)
                else:
                    self._global_container_stack.extruders[position].material = empty_material_container
                self.updateMaterialWithVariant(position)

            if configuration.buildplateConfiguration is not None:
                global_variant_container_node = self._variant_manager.getBuildplateVariantNode(self._global_container_stack.definition.getId(), configuration.buildplateConfiguration)
                if global_variant_container_node:
                    self._setGlobalVariant(global_variant_container_node)
                else:
                    self._global_container_stack.variant = empty_variant_container
            else:
                self._global_container_stack.variant = empty_variant_container
            self._updateQualityWithMaterial()

        # See if we need to show the Discard or Keep changes screen
        if self.hasUserSettings and self._application.getPreferences().getValue("cura/active_mode") == 1:
            self._application.discardOrKeepProfileChanges()

    ##  Find all container stacks that has the pair 'key = value' in its metadata and replaces the value with 'new_value'
    def replaceContainersMetadata(self, key: str, value: str, new_value: str) -> None:
        machines = CuraContainerRegistry.getInstance().findContainerStacks(type = "machine")
        for machine in machines:
            if machine.getMetaDataEntry(key) == value:
                machine.setMetaDataEntry(key, new_value)

    ##  This method checks if the name of the group stored in the definition container is correct.
    #   After updating from 3.2 to 3.3 some group names may be temporary. If there is a mismatch in the name of the group
    #   then all the container stacks are updated, both the current and the hidden ones.
    def checkCorrectGroupName(self, device_id: str, group_name: str) -> None:
        if self._global_container_stack and device_id == self.activeMachineNetworkKey:
            # Check if the connect_group_name is correct. If not, update all the containers connected to the same printer
            if self.activeMachineNetworkGroupName != group_name:
                metadata_filter = {"um_network_key": self.activeMachineNetworkKey}
                containers = CuraContainerRegistry.getInstance().findContainerStacks(type = "machine", **metadata_filter)
                for container in containers:
                    container.setMetaDataEntry("connect_group_name", group_name)

    ##  This method checks if there is an instance connected to the given network_key
    def existNetworkInstances(self, network_key: str) -> bool:
        metadata_filter = {"um_network_key": network_key}
        containers = CuraContainerRegistry.getInstance().findContainerStacks(type = "machine", **metadata_filter)
        return bool(containers)

    @pyqtSlot("QVariant")
    def setGlobalVariant(self, container_node: "ContainerNode") -> None:
        self.blurSettings.emit()
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self._setGlobalVariant(container_node)
            self.updateMaterialWithVariant(None)  # Update all materials
            self._updateQualityWithMaterial()

    @pyqtSlot(str, str)
    def setMaterialById(self, position: str, root_material_id: str) -> None:
        if self._global_container_stack is None:
            return
        buildplate_name = None
        if self._global_container_stack.variant.getId() != "empty_variant":
            buildplate_name = self._global_container_stack.variant.getName()

        machine_definition_id = self._global_container_stack.definition.id
        position = str(position)
        extruder_stack = self._global_container_stack.extruders[position]
        nozzle_name = extruder_stack.variant.getName()
        material_diameter = extruder_stack.getApproximateMaterialDiameter()
        material_node = self._material_manager.getMaterialNode(machine_definition_id, nozzle_name, buildplate_name,
                                                               material_diameter, root_material_id)
        self.setMaterial(position, material_node)

    ##  global_stack: if you want to provide your own global_stack instead of the current active one
    #   if you update an active machine, special measures have to be taken.
    @pyqtSlot(str, "QVariant")
    def setMaterial(self, position: str, container_node, global_stack: Optional["GlobalStack"] = None) -> None:
        if global_stack is not None and global_stack != self._global_container_stack:
            global_stack.extruders[position].material = container_node.getContainer()
            return
        position = str(position)
        self.blurSettings.emit()
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self._setMaterial(position, container_node)
            self._updateQualityWithMaterial()

        # See if we need to show the Discard or Keep changes screen
        if self.hasUserSettings and self._application.getPreferences().getValue("cura/active_mode") == 1:
            self._application.discardOrKeepProfileChanges()

    @pyqtSlot(str, str)
    def setVariantByName(self, position: str, variant_name: str) -> None:
        if self._global_container_stack is None:
            return
        machine_definition_id = self._global_container_stack.definition.id
        variant_node = self._variant_manager.getVariantNode(machine_definition_id, variant_name)
        self.setVariant(position, variant_node)

    @pyqtSlot(str, "QVariant")
    def setVariant(self, position: str, container_node: "ContainerNode") -> None:
        position = str(position)
        self.blurSettings.emit()
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self._setVariantNode(position, container_node)
            self.updateMaterialWithVariant(position)
            self._updateQualityWithMaterial()

        # See if we need to show the Discard or Keep changes screen
        if self.hasUserSettings and self._application.getPreferences().getValue("cura/active_mode") == 1:
            self._application.discardOrKeepProfileChanges()

    @pyqtSlot(str)
    def setQualityGroupByQualityType(self, quality_type: str) -> None:
        if self._global_container_stack is None:
            return
        # Get all the quality groups for this global stack and filter out by quality_type
        quality_group_dict = self._quality_manager.getQualityGroups(self._global_container_stack)
        quality_group = quality_group_dict[quality_type]
        self.setQualityGroup(quality_group)

    ##  Optionally provide global_stack if you want to use your own
    #   The active global_stack is treated differently.
    @pyqtSlot(QObject)
    def setQualityGroup(self, quality_group: "QualityGroup", no_dialog: bool = False, global_stack: Optional["GlobalStack"] = None) -> None:
        if global_stack is not None and global_stack != self._global_container_stack:
            if quality_group is None:
                Logger.log("e", "Could not set quality group because quality group is None")
                return
            if quality_group.node_for_global is None:
                Logger.log("e", "Could not set quality group [%s] because it has no node_for_global", str(quality_group))
                return
            # This is not changing the quality for the active machine !!!!!!!!
            global_stack.quality = quality_group.node_for_global.getContainer()
            for extruder_nr, extruder_stack in global_stack.extruders.items():
                quality_container = empty_quality_container
                if extruder_nr in quality_group.nodes_for_extruders:
                    container = quality_group.nodes_for_extruders[extruder_nr].getContainer()
                    quality_container = container if container is not None else quality_container
                extruder_stack.quality = quality_container
            return

        self.blurSettings.emit()
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self._setQualityGroup(quality_group)

        # See if we need to show the Discard or Keep changes screen
        if not no_dialog and self.hasUserSettings and self._application.getPreferences().getValue("cura/active_mode") == 1:
            self._application.discardOrKeepProfileChanges()

    @pyqtProperty(QObject, fset = setQualityGroup, notify = activeQualityGroupChanged)
    def activeQualityGroup(self) -> Optional["QualityGroup"]:
        return self._current_quality_group

    @pyqtSlot(QObject)
    def setQualityChangesGroup(self, quality_changes_group: "QualityChangesGroup", no_dialog: bool = False) -> None:
        self.blurSettings.emit()
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self._setQualityChangesGroup(quality_changes_group)

        # See if we need to show the Discard or Keep changes screen
        if not no_dialog and self.hasUserSettings and self._application.getPreferences().getValue("cura/active_mode") == 1:
            self._application.discardOrKeepProfileChanges()

    @pyqtSlot()
    def resetToUseDefaultQuality(self) -> None:
        if self._global_container_stack is None:
            return
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self._setQualityGroup(self._current_quality_group)
            for stack in [self._global_container_stack] + list(self._global_container_stack.extruders.values()):
                stack.userChanges.clear()

    @pyqtProperty(QObject, fset = setQualityChangesGroup, notify = activeQualityChangesGroupChanged)
    def activeQualityChangesGroup(self) -> Optional["QualityChangesGroup"]:
        return self._current_quality_changes_group

    @pyqtProperty(str, notify = activeQualityGroupChanged)
    def activeQualityOrQualityChangesName(self) -> str:
        name = empty_quality_container.getName()
        if self._current_quality_changes_group:
            name = self._current_quality_changes_group.name
        elif self._current_quality_group:
            name = self._current_quality_group.name
        return name

    def _updateUponMaterialMetadataChange(self) -> None:
        if self._global_container_stack is None:
            return
        with postponeSignals(*self._getContainerChangedSignals(), compress = CompressTechnique.CompressPerParameterValue):
            self.updateMaterialWithVariant(None)
            self._updateQualityWithMaterial()
