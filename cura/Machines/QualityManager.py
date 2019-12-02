# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from typing import TYPE_CHECKING, Optional, cast, Dict, List, Set

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from UM.ConfigurationErrorMessage import ConfigurationErrorMessage
from UM.Logger import Logger
from UM.Util import parseBool
from UM.Settings.InstanceContainer import InstanceContainer

from cura.Settings.ExtruderStack import ExtruderStack

from .QualityGroup import QualityGroup
from .QualityNode import QualityNode

if TYPE_CHECKING:
    from UM.Settings.DefinitionContainer import DefinitionContainer
    from cura.Settings.GlobalStack import GlobalStack
    from .QualityChangesGroup import QualityChangesGroup
    from cura.CuraApplication import CuraApplication


#
# Similar to MaterialManager, QualityManager maintains a number of maps and trees for quality profile lookup.
# The models GUI and QML use are now only dependent on the QualityManager. That means as long as the data in
# QualityManager gets updated correctly, the GUI models should be updated correctly too, and the same goes for GUI.
#
# For now, updating the lookup maps and trees here is very simple: we discard the old data completely and recreate them
# again. This means the update is exactly the same as initialization. There are performance concerns about this approach
# but so far the creation of the tables and maps is very fast and there is no noticeable slowness, we keep it like this
# because it's simple.
#
class QualityManager(QObject):

    qualitiesUpdated = pyqtSignal()

    def __init__(self, application: "CuraApplication", parent = None) -> None:
        super().__init__(parent)
        self._application = application
        self._material_manager = self._application.getMaterialManager()
        self._container_registry = self._application.getContainerRegistry()

        self._empty_quality_container = self._application.empty_quality_container
        self._empty_quality_changes_container = self._application.empty_quality_changes_container

        # For quality lookup
        self._machine_nozzle_buildplate_material_quality_type_to_quality_dict = {}  # type: Dict[str, QualityNode]

        # For quality_changes lookup
        self._machine_quality_type_to_quality_changes_dict = {}  # type: Dict[str, QualityNode]

        self._default_machine_definition_id = "fdmprinter"

        self._container_registry.containerMetaDataChanged.connect(self._onContainerMetadataChanged)
        self._container_registry.containerAdded.connect(self._onContainerMetadataChanged)
        self._container_registry.containerRemoved.connect(self._onContainerMetadataChanged)

        # When a custom quality gets added/imported, there can be more than one InstanceContainers. In those cases,
        # we don't want to react on every container/metadata changed signal. The timer here is to buffer it a bit so
        # we don't react too many time.
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(300)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._updateMaps)

    def initialize(self) -> None:
        # Initialize the lookup tree for quality profiles with following structure:
        # <machine> -> <nozzle> -> <buildplate> -> <material>
        # <machine> -> <material>

        self._machine_nozzle_buildplate_material_quality_type_to_quality_dict = {}  # for quality lookup
        self._machine_quality_type_to_quality_changes_dict = {}  # for quality_changes lookup

        quality_metadata_list = self._container_registry.findContainersMetadata(type = "quality")
        for metadata in quality_metadata_list:
            if metadata["id"] == "empty_quality":
                continue

            definition_id = metadata["definition"]
            quality_type = metadata["quality_type"]

            root_material_id = metadata.get("material")
            nozzle_name = metadata.get("variant")
            buildplate_name = metadata.get("buildplate")
            is_global_quality = metadata.get("global_quality", False)
            is_global_quality = is_global_quality or (root_material_id is None and nozzle_name is None and buildplate_name is None)

            # Sanity check: material+variant and is_global_quality cannot be present at the same time
            if is_global_quality and (root_material_id or nozzle_name):
                ConfigurationErrorMessage.getInstance().addFaultyContainers(metadata["id"])
                continue

            if definition_id not in self._machine_nozzle_buildplate_material_quality_type_to_quality_dict:
                self._machine_nozzle_buildplate_material_quality_type_to_quality_dict[definition_id] = QualityNode()
            machine_node = cast(QualityNode, self._machine_nozzle_buildplate_material_quality_type_to_quality_dict[definition_id])

            if is_global_quality:
                # For global qualities, save data in the machine node
                machine_node.addQualityMetadata(quality_type, metadata)
                continue

            current_node = machine_node
            intermediate_node_info_list = [nozzle_name, buildplate_name, root_material_id]
            current_intermediate_node_info_idx = 0

            while current_intermediate_node_info_idx < len(intermediate_node_info_list):
                node_name = intermediate_node_info_list[current_intermediate_node_info_idx]
                if node_name is not None:
                    # There is specific information, update the current node to go deeper so we can add this quality
                    # at the most specific branch in the lookup tree.
                    if node_name not in current_node.children_map:
                        current_node.children_map[node_name] = QualityNode()
                    current_node = cast(QualityNode, current_node.children_map[node_name])

                current_intermediate_node_info_idx += 1

            current_node.addQualityMetadata(quality_type, metadata)

        # Initialize the lookup tree for quality_changes profiles with following structure:
        # <machine> -> <quality_type> -> <name>
        quality_changes_metadata_list = self._container_registry.findContainersMetadata(type = "quality_changes")
        for metadata in quality_changes_metadata_list:
            if metadata["id"] == "empty_quality_changes":
                continue

            machine_definition_id = metadata["definition"]
            quality_type = metadata["quality_type"]

            if machine_definition_id not in self._machine_quality_type_to_quality_changes_dict:
                self._machine_quality_type_to_quality_changes_dict[machine_definition_id] = QualityNode()
            machine_node = self._machine_quality_type_to_quality_changes_dict[machine_definition_id]
            machine_node.addQualityChangesMetadata(quality_type, metadata)

        Logger.log("d", "Lookup tables updated.")
        self.qualitiesUpdated.emit()

    def _updateMaps(self) -> None:
        self.initialize()

    def _onContainerMetadataChanged(self, container: InstanceContainer) -> None:
        self._onContainerChanged(container)

    def _onContainerChanged(self, container: InstanceContainer) -> None:
        container_type = container.getMetaDataEntry("type")
        if container_type not in ("quality", "quality_changes"):
            return

        # update the cache table
        self._update_timer.start()

    # Updates the given quality groups' availabilities according to which extruders are being used/ enabled.
    def _updateQualityGroupsAvailability(self, machine: "GlobalStack", quality_group_list) -> None:
        used_extruders = set()
        for i in range(machine.getProperty("machine_extruder_count", "value")):
            if str(i) in machine.extruders and machine.extruders[str(i)].isEnabled:
                used_extruders.add(str(i))

        # Update the "is_available" flag for each quality group.
        for quality_group in quality_group_list:
            is_available = True
            if quality_group.node_for_global is None:
                is_available = False
            if is_available:
                for position in used_extruders:
                    if position not in quality_group.nodes_for_extruders:
                        is_available = False
                        break

            quality_group.is_available = is_available

    # Returns a dict of "custom profile name" -> QualityChangesGroup
    def getQualityChangesGroups(self, machine: "GlobalStack") -> dict:
        machine_definition_id = getMachineDefinitionIDForQualitySearch(machine.definition)

        machine_node = self._machine_quality_type_to_quality_changes_dict.get(machine_definition_id)
        if not machine_node:
            Logger.log("i", "Cannot find node for machine def [%s] in QualityChanges lookup table", machine_definition_id)
            return dict()

        # Update availability for each QualityChangesGroup:
        # A custom profile is always available as long as the quality_type it's based on is available
        quality_group_dict = self.getQualityGroups(machine)
        available_quality_type_list = [qt for qt, qg in quality_group_dict.items() if qg.is_available]

        # Iterate over all quality_types in the machine node
        quality_changes_group_dict = dict()
        for quality_type, quality_changes_node in machine_node.quality_type_map.items():
            for quality_changes_name, quality_changes_group in quality_changes_node.children_map.items():
                quality_changes_group_dict[quality_changes_name] = quality_changes_group
                quality_changes_group.is_available = quality_type in available_quality_type_list

        return quality_changes_group_dict

    #
    # Gets all quality groups for the given machine. Both available and none available ones will be included.
    # It returns a dictionary with "quality_type"s as keys and "QualityGroup"s as values.
    # Whether a QualityGroup is available can be unknown via the field QualityGroup.is_available.
    # For more details, see QualityGroup.
    #
    def getQualityGroups(self, machine: "GlobalStack") -> Dict[str, QualityGroup]:
        machine_definition_id = getMachineDefinitionIDForQualitySearch(machine.definition)

        # This determines if we should only get the global qualities for the global stack and skip the global qualities for the extruder stacks
        has_machine_specific_qualities = machine.getHasMachineQuality()

        # To find the quality container for the GlobalStack, check in the following fall-back manner:
        #   (1) the machine-specific node
        #   (2) the generic node
        machine_node = self._machine_nozzle_buildplate_material_quality_type_to_quality_dict.get(machine_definition_id)
        # Check if this machine has specific quality profiles for its extruders, if so, when looking up extruder
        # qualities, we should not fall back to use the global qualities.
        has_extruder_specific_qualities = False
        if machine_node:
            if machine_node.children_map:
                has_extruder_specific_qualities = True

        default_machine_node = self._machine_nozzle_buildplate_material_quality_type_to_quality_dict.get(self._default_machine_definition_id)

        nodes_to_check = []  # type: List[QualityNode]
        if machine_node is not None:
            nodes_to_check.append(machine_node)
        if default_machine_node is not None:
            nodes_to_check.append(default_machine_node)

        # Iterate over all quality_types in the machine node
        quality_group_dict = {}
        for node in nodes_to_check:
            if node and node.quality_type_map:
                quality_node = list(node.quality_type_map.values())[0]
                is_global_quality = parseBool(quality_node.getMetaDataEntry("global_quality", False))
                if not is_global_quality:
                    continue

                for quality_type, quality_node in node.quality_type_map.items():
                    quality_group = QualityGroup(quality_node.getMetaDataEntry("name", ""), quality_type)
                    quality_group.node_for_global = quality_node
                    quality_group_dict[quality_type] = quality_group
                break

        buildplate_name = machine.getBuildplateName()

        # Iterate over all extruders to find quality containers for each extruder
        for position, extruder in machine.extruders.items():
            nozzle_name = None
            if extruder.variant.getId() != "empty_variant":
                nozzle_name = extruder.variant.getName()

            # This is a list of root material IDs to use for searching for suitable quality profiles.
            # The root material IDs in this list are in prioritized order.
            root_material_id_list = []
            has_material = False  # flag indicating whether this extruder has a material assigned
            root_material_id = None
            if extruder.material.getId() != "empty_material":
                has_material = True
                root_material_id = extruder.material.getMetaDataEntry("base_file")
                # Convert possible generic_pla_175 -> generic_pla
                root_material_id = self._material_manager.getRootMaterialIDWithoutDiameter(root_material_id)
                root_material_id_list.append(root_material_id)

                # Also try to get the fallback materials
                fallback_ids = self._material_manager.getFallBackMaterialIdsByMaterial(extruder.material)

                if fallback_ids:
                    root_material_id_list.extend(fallback_ids)

                # Weed out duplicates while preserving the order.
                seen = set()  # type: Set[str]
                root_material_id_list = [x for x in root_material_id_list if x not in seen and not seen.add(x)]  # type: ignore

            # Here we construct a list of nodes we want to look for qualities with the highest priority first.
            # The use case is that, when we look for qualities for a machine, we first want to search in the following
            # order:
            #   1. machine-nozzle-buildplate-and-material-specific qualities if exist
            #   2. machine-nozzle-and-material-specific qualities if exist
            #   3. machine-nozzle-specific qualities if exist
            #   4. machine-material-specific qualities if exist
            #   5. machine-specific global qualities if exist, otherwise generic global qualities
            #      NOTE: We DO NOT fail back to generic global qualities if machine-specific global qualities exist.
            #            This is because when a machine defines its own global qualities such as Normal, Fine, etc.,
            #            it is intended to maintain those specific qualities ONLY. If we still fail back to the generic
            #            global qualities, there can be unimplemented quality types e.g. "coarse", and this is not
            #            correct.
            # Each points above can be represented as a node in the lookup tree, so here we simply put those nodes into
            # the list with priorities as the order. Later, we just need to loop over each node in this list and fetch
            # qualities from there.
            node_info_list_0 = [nozzle_name, buildplate_name, root_material_id]  # type: List[Optional[str]]
            nodes_to_check = []

            # This function tries to recursively find the deepest (the most specific) branch and add those nodes to
            # the search list in the order described above. So, by iterating over that search node list, we first look
            # in the more specific branches and then the less specific (generic) ones.
            def addNodesToCheck(node: Optional[QualityNode], nodes_to_check_list: List[QualityNode], node_info_list, node_info_idx: int) -> None:
                if node is None:
                    return

                if node_info_idx < len(node_info_list):
                    node_name = node_info_list[node_info_idx]
                    if node_name is not None:
                        current_node = node.getChildNode(node_name)
                        if current_node is not None and has_material:
                            addNodesToCheck(current_node, nodes_to_check_list, node_info_list, node_info_idx + 1)

                if has_material:
                    for rmid in root_material_id_list:
                        material_node = node.getChildNode(rmid)
                        if material_node:
                            nodes_to_check_list.append(material_node)
                            break

                nodes_to_check_list.append(node)

            addNodesToCheck(machine_node, nodes_to_check, node_info_list_0, 0)

            # The last fall back will be the global qualities (either from the machine-specific node or the generic
            # node), but we only use one. For details see the overview comments above.

            if machine_node is not None and machine_node.quality_type_map:
                nodes_to_check += [machine_node]
            elif default_machine_node is not None:
                nodes_to_check += [default_machine_node]

            for node_idx, node in enumerate(nodes_to_check):
                if node and node.quality_type_map:
                    if has_extruder_specific_qualities:
                        # Only include variant qualities; skip non global qualities
                        quality_node = list(node.quality_type_map.values())[0]
                        is_global_quality = parseBool(quality_node.getMetaDataEntry("global_quality", False))
                        if is_global_quality:
                            continue

                    for quality_type, quality_node in node.quality_type_map.items():
                        if quality_type not in quality_group_dict:
                            quality_group = QualityGroup(quality_node.getMetaDataEntry("name", ""), quality_type)
                            quality_group_dict[quality_type] = quality_group

                        quality_group = quality_group_dict[quality_type]
                        if position not in quality_group.nodes_for_extruders:
                            quality_group.nodes_for_extruders[position] = quality_node

                # If the machine has its own specific qualities, for extruders, it should skip the global qualities
                # and use the material/variant specific qualities.
                if has_extruder_specific_qualities:
                    if node_idx == len(nodes_to_check) - 1:
                        break

        # Update availabilities for each quality group
        self._updateQualityGroupsAvailability(machine, quality_group_dict.values())

        return quality_group_dict

    def getQualityGroupsForMachineDefinition(self, machine: "GlobalStack") -> Dict[str, QualityGroup]:
        machine_definition_id = getMachineDefinitionIDForQualitySearch(machine.definition)

        # To find the quality container for the GlobalStack, check in the following fall-back manner:
        #   (1) the machine-specific node
        #   (2) the generic node
        machine_node = self._machine_nozzle_buildplate_material_quality_type_to_quality_dict.get(machine_definition_id)
        default_machine_node = self._machine_nozzle_buildplate_material_quality_type_to_quality_dict.get(
            self._default_machine_definition_id)
        nodes_to_check = [machine_node, default_machine_node]

        # Iterate over all quality_types in the machine node
        quality_group_dict = dict()
        for node in nodes_to_check:
            if node and node.quality_type_map:
                for quality_type, quality_node in node.quality_type_map.items():
                    quality_group = QualityGroup(quality_node.getMetaDataEntry("name", ""), quality_type)
                    quality_group.node_for_global = quality_node
                    quality_group_dict[quality_type] = quality_group
                break

        return quality_group_dict

    def getDefaultQualityType(self, machine: "GlobalStack") -> Optional[QualityGroup]:
        preferred_quality_type = machine.definition.getMetaDataEntry("preferred_quality_type")
        quality_group_dict = self.getQualityGroups(machine)
        quality_group = quality_group_dict.get(preferred_quality_type)
        return quality_group


    #
    # Methods for GUI
    #

    #
    # Remove the given quality changes group.
    #
    @pyqtSlot(QObject)
    def removeQualityChangesGroup(self, quality_changes_group: "QualityChangesGroup") -> None:
        Logger.log("i", "Removing quality changes group [%s]", quality_changes_group.name)
        removed_quality_changes_ids = set()
        for node in quality_changes_group.getAllNodes():
            container_id = node.getMetaDataEntry("id")
            self._container_registry.removeContainer(container_id)
            removed_quality_changes_ids.add(container_id)

        # Reset all machines that have activated this quality changes to empty.
        for global_stack in self._container_registry.findContainerStacks(type = "machine"):
            if global_stack.qualityChanges.getId() in removed_quality_changes_ids:
                global_stack.qualityChanges = self._empty_quality_changes_container
        for extruder_stack in self._container_registry.findContainerStacks(type = "extruder_train"):
            if extruder_stack.qualityChanges.getId() in removed_quality_changes_ids:
                extruder_stack.qualityChanges = self._empty_quality_changes_container

    #
    # Rename a set of quality changes containers. Returns the new name.
    #
    @pyqtSlot(QObject, str, result = str)
    def renameQualityChangesGroup(self, quality_changes_group: "QualityChangesGroup", new_name: str) -> str:
        Logger.log("i", "Renaming QualityChangesGroup[%s] to [%s]", quality_changes_group.name, new_name)
        if new_name == quality_changes_group.name:
            Logger.log("i", "QualityChangesGroup name [%s] unchanged.", quality_changes_group.name)
            return new_name

        new_name = self._container_registry.uniqueName(new_name)
        for node in quality_changes_group.getAllNodes():
            container = node.getContainer()
            if container:
                container.setName(new_name)

        quality_changes_group.name = new_name

        self._application.getMachineManager().activeQualityChanged.emit()
        self._application.getMachineManager().activeQualityGroupChanged.emit()

        return new_name

    #
    # Duplicates the given quality.
    #
    @pyqtSlot(str, "QVariantMap")
    def duplicateQualityChanges(self, quality_changes_name: str, quality_model_item) -> None:
        global_stack = self._application.getGlobalContainerStack()
        if not global_stack:
            Logger.log("i", "No active global stack, cannot duplicate quality changes.")
            return

        quality_group = quality_model_item["quality_group"]
        quality_changes_group = quality_model_item["quality_changes_group"]
        if quality_changes_group is None:
            # create global quality changes only
            new_quality_changes = self._createQualityChanges(quality_group.quality_type, quality_changes_name,
                                                             global_stack, None)
            self._container_registry.addContainer(new_quality_changes)
        else:
            new_name = self._container_registry.uniqueName(quality_changes_name)
            for node in quality_changes_group.getAllNodes():
                container = node.getContainer()
                if not container:
                    continue
                new_id = self._container_registry.uniqueName(container.getId())
                self._container_registry.addContainer(container.duplicate(new_id, new_name))

    ##  Create quality changes containers from the user containers in the active stacks.
    #
    #   This will go through the global and extruder stacks and create quality_changes containers from
    #   the user containers in each stack. These then replace the quality_changes containers in the
    #   stack and clear the user settings.
    @pyqtSlot(str)
    def createQualityChanges(self, base_name: str) -> None:
        machine_manager = self._application.getMachineManager()

        global_stack = machine_manager.activeMachine
        if not global_stack:
            return

        active_quality_name = machine_manager.activeQualityOrQualityChangesName
        if active_quality_name == "":
            Logger.log("w", "No quality container found in stack %s, cannot create profile", global_stack.getId())
            return

        machine_manager.blurSettings.emit()
        if base_name is None or base_name == "":
            base_name = active_quality_name
        unique_name = self._container_registry.uniqueName(base_name)

        # Go through the active stacks and create quality_changes containers from the user containers.
        stack_list = [global_stack] + list(global_stack.extruders.values())
        for stack in stack_list:
            user_container = stack.userChanges
            quality_container = stack.quality
            quality_changes_container = stack.qualityChanges
            if not quality_container or not quality_changes_container:
                Logger.log("w", "No quality or quality changes container found in stack %s, ignoring it", stack.getId())
                continue

            quality_type = quality_container.getMetaDataEntry("quality_type")
            extruder_stack = None
            if isinstance(stack, ExtruderStack):
                extruder_stack = stack
            new_changes = self._createQualityChanges(quality_type, unique_name, global_stack, extruder_stack)
            from cura.Settings.ContainerManager import ContainerManager
            ContainerManager.getInstance()._performMerge(new_changes, quality_changes_container, clear_settings = False)
            ContainerManager.getInstance()._performMerge(new_changes, user_container)

            self._container_registry.addContainer(new_changes)

    #
    # Create a quality changes container with the given setup.
    #
    def _createQualityChanges(self, quality_type: str, new_name: str, machine: "GlobalStack",
                              extruder_stack: Optional["ExtruderStack"]) -> "InstanceContainer":
        base_id = machine.definition.getId() if extruder_stack is None else extruder_stack.getId()
        new_id = base_id + "_" + new_name
        new_id = new_id.lower().replace(" ", "_")
        new_id = self._container_registry.uniqueName(new_id)

        # Create a new quality_changes container for the quality.
        quality_changes = InstanceContainer(new_id)
        quality_changes.setName(new_name)
        quality_changes.setMetaDataEntry("type", "quality_changes")
        quality_changes.setMetaDataEntry("quality_type", quality_type)

        # If we are creating a container for an extruder, ensure we add that to the container
        if extruder_stack is not None:
            quality_changes.setMetaDataEntry("position", extruder_stack.getMetaDataEntry("position"))

        # If the machine specifies qualities should be filtered, ensure we match the current criteria.
        machine_definition_id = getMachineDefinitionIDForQualitySearch(machine.definition)
        quality_changes.setDefinition(machine_definition_id)

        quality_changes.setMetaDataEntry("setting_version", self._application.SettingVersion)
        return quality_changes


#
# Gets the machine definition ID that can be used to search for Quality containers that are suitable for the given
# machine. The rule is as follows:
#   1. By default, the machine definition ID for quality container search will be "fdmprinter", which is the generic
#      machine.
#   2. If a machine has its own machine quality (with "has_machine_quality = True"), we should use the given machine's
#      own machine definition ID for quality search.
#      Example: for an Ultimaker 3, the definition ID should be "ultimaker3".
#   3. When condition (2) is met, AND the machine has "quality_definition" defined in its definition file, then the
#      definition ID specified in "quality_definition" should be used.
#      Example: for an Ultimaker 3 Extended, it has "quality_definition = ultimaker3". This means Ultimaker 3 Extended
#               shares the same set of qualities profiles as Ultimaker 3.
#
def getMachineDefinitionIDForQualitySearch(machine_definition: "DefinitionContainer",
                                           default_definition_id: str = "fdmprinter") -> str:
    machine_definition_id = default_definition_id
    if parseBool(machine_definition.getMetaDataEntry("has_machine_quality", False)):
        # Only use the machine's own quality definition ID if this machine has machine quality.
        machine_definition_id = machine_definition.getMetaDataEntry("quality_definition")
        if machine_definition_id is None:
            machine_definition_id = machine_definition.getId()

    return machine_definition_id
