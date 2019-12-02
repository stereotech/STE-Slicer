# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from typing import Optional

from UM.ConfigurationErrorMessage import ConfigurationErrorMessage
from UM.Logger import Logger
from UM.Settings.Interfaces import DefinitionContainerInterface
from UM.Settings.InstanceContainer import InstanceContainer

from cura.Machines.VariantType import VariantType
from .GlobalStack import GlobalStack
from .ExtruderStack import ExtruderStack


##  Contains helper functions to create new machines.
class CuraStackBuilder:

    ##  Create a new instance of a machine.
    #
    #   \param name The name of the new machine.
    #   \param definition_id The ID of the machine definition to use.
    #
    #   \return The new global stack or None if an error occurred.
    @classmethod
    def createMachine(cls, name: str, definition_id: str) -> Optional[GlobalStack]:
        from cura.CuraApplication import CuraApplication
        application = CuraApplication.getInstance()
        variant_manager = application.getVariantManager()
        quality_manager = application.getQualityManager()
        registry = application.getContainerRegistry()

        definitions = registry.findDefinitionContainers(id = definition_id)
        if not definitions:
            ConfigurationErrorMessage.getInstance().addFaultyContainers(definition_id)
            Logger.log("w", "Definition {definition} was not found!", definition = definition_id)
            return None

        machine_definition = definitions[0]

        # get variant container for the global stack
        global_variant_container = application.empty_variant_container
        global_variant_node = variant_manager.getDefaultVariantNode(machine_definition, VariantType.BUILD_PLATE)
        if global_variant_node:
            global_variant_container = global_variant_node.getContainer()
        if not global_variant_container:
            global_variant_container = application.empty_variant_container

        generated_name = registry.createUniqueName("machine", "", name, machine_definition.getName())
        # Make sure the new name does not collide with any definition or (quality) profile
        # createUniqueName() only looks at other stacks, but not at definitions or quality profiles
        # Note that we don't go for uniqueName() immediately because that function matches with ignore_case set to true
        if registry.findContainersMetadata(id = generated_name):
            generated_name = registry.uniqueName(generated_name)

        new_global_stack = cls.createGlobalStack(
            new_stack_id = generated_name,
            definition = machine_definition,
            variant_container = global_variant_container,
            material_container = application.empty_material_container,
            quality_container = application.empty_quality_container,
        )
        new_global_stack.setName(generated_name)

        # Create ExtruderStacks
        extruder_dict = machine_definition.getMetaDataEntry("machine_extruder_trains")
        for position in extruder_dict:
            cls.createExtruderStackWithDefaultSetup(new_global_stack, position)

        for new_extruder in new_global_stack.extruders.values(): #Only register the extruders if we're sure that all of them are correct.
            registry.addContainer(new_extruder)

        preferred_quality_type = machine_definition.getMetaDataEntry("preferred_quality_type")
        quality_group_dict = quality_manager.getQualityGroups(new_global_stack)
        if not quality_group_dict:
            # There is no available quality group, set all quality containers to empty.
            new_global_stack.quality = application.empty_quality_container
            for extruder_stack in new_global_stack.extruders.values():
                extruder_stack.quality = application.empty_quality_container
        else:
            # Set the quality containers to the preferred quality type if available, otherwise use the first quality
            # type that's available.
            if preferred_quality_type not in quality_group_dict:
                Logger.log("w", "The preferred quality {quality_type} doesn't exist for this set-up. Choosing a random one.".format(quality_type = preferred_quality_type))
                preferred_quality_type = next(iter(quality_group_dict))
            quality_group = quality_group_dict.get(preferred_quality_type)

            new_global_stack.quality = quality_group.node_for_global.getContainer()
            if not new_global_stack.quality:
                new_global_stack.quality = application.empty_quality_container
            for position, extruder_stack in new_global_stack.extruders.items():
                if position in quality_group.nodes_for_extruders and quality_group.nodes_for_extruders[position].getContainer():
                    extruder_stack.quality = quality_group.nodes_for_extruders[position].getContainer()
                else:
                    extruder_stack.quality = application.empty_quality_container

        # Register the global stack after the extruder stacks are created. This prevents the registry from adding another
        # extruder stack because the global stack didn't have one yet (which is enforced since Cura 3.1).
        registry.addContainer(new_global_stack)

        return new_global_stack

    ##  Create a default Extruder Stack
    #
    #   \param global_stack The global stack this extruder refers to.
    #   \param extruder_position The position of the current extruder.
    @classmethod
    def createExtruderStackWithDefaultSetup(cls, global_stack: "GlobalStack", extruder_position: int) -> None:
        from cura.CuraApplication import CuraApplication
        application = CuraApplication.getInstance()
        variant_manager = application.getVariantManager()
        material_manager = application.getMaterialManager()
        registry = application.getContainerRegistry()

        # get variant container for extruders
        extruder_variant_container = application.empty_variant_container
        extruder_variant_node = variant_manager.getDefaultVariantNode(global_stack.definition, VariantType.NOZZLE,
                                                                      global_stack = global_stack)
        extruder_variant_name = None
        if extruder_variant_node:
            extruder_variant_container = extruder_variant_node.getContainer()
            if not extruder_variant_container:
                extruder_variant_container = application.empty_variant_container
            extruder_variant_name = extruder_variant_container.getName()

        extruder_definition_dict = global_stack.getMetaDataEntry("machine_extruder_trains")
        extruder_definition_id = extruder_definition_dict[str(extruder_position)]
        extruder_definition = registry.findDefinitionContainers(id = extruder_definition_id)[0]

        # get material container for extruders
        material_container = application.empty_material_container
        material_node = material_manager.getDefaultMaterial(global_stack, str(extruder_position), extruder_variant_name,
                                                            extruder_definition = extruder_definition)
        if material_node and material_node.getContainer():
            material_container = material_node.getContainer()

        new_extruder_id = registry.uniqueName(extruder_definition_id)
        new_extruder = cls.createExtruderStack(
            new_extruder_id,
            extruder_definition = extruder_definition,
            machine_definition_id = global_stack.definition.getId(),
            position = extruder_position,
            variant_container = extruder_variant_container,
            material_container = material_container,
            quality_container = application.empty_quality_container
        )
        new_extruder.setNextStack(global_stack)

        registry.addContainer(new_extruder)

    ##  Create a new Extruder stack
    #
    #   \param new_stack_id The ID of the new stack.
    #   \param extruder_definition The definition to base the new stack on.
    #   \param machine_definition_id The ID of the machine definition to use for the user container.
    #   \param position The position the extruder occupies in the machine.
    #   \param variant_container The variant selected for the current extruder.
    #   \param material_container The material selected for the current extruder.
    #   \param quality_container The quality selected for the current extruder.
    #
    #   \return A new Extruder stack instance with the specified parameters.
    @classmethod
    def createExtruderStack(cls, new_stack_id: str, extruder_definition: DefinitionContainerInterface,
                            machine_definition_id: str,
                            position: int,
                            variant_container: "InstanceContainer",
                            material_container: "InstanceContainer",
                            quality_container: "InstanceContainer") -> ExtruderStack:

        from cura.CuraApplication import CuraApplication
        application = CuraApplication.getInstance()
        registry = application.getContainerRegistry()

        stack = ExtruderStack(new_stack_id)
        stack.setName(extruder_definition.getName())
        stack.setDefinition(extruder_definition)

        stack.setMetaDataEntry("position", str(position))

        user_container = cls.createUserChangesContainer(new_stack_id + "_user", machine_definition_id, new_stack_id,
                                                        is_global_stack = False)

        stack.definitionChanges = cls.createDefinitionChangesContainer(stack, new_stack_id + "_settings")
        stack.variant = variant_container
        stack.material = material_container
        stack.quality = quality_container
        stack.qualityChanges = application.empty_quality_changes_container
        stack.userChanges = user_container

        # Only add the created containers to the registry after we have set all the other
        # properties. This makes the create operation more transactional, since any problems
        # setting properties will not result in incomplete containers being added.
        registry.addContainer(user_container)

        return stack

    ##  Create a new Global stack
    #
    #   \param new_stack_id The ID of the new stack.
    #   \param definition The definition to base the new stack on.
    #   \param kwargs You can add keyword arguments to specify IDs of containers to use for a specific type, for example "variant": "0.4mm"
    #
    #   \return A new Global stack instance with the specified parameters.

    ##  Create a new Global stack
    #
    #   \param new_stack_id The ID of the new stack.
    #   \param definition The definition to base the new stack on.
    #   \param variant_container The variant selected for the current stack.
    #   \param material_container The material selected for the current stack.
    #   \param quality_container The quality selected for the current stack.
    #
    #   \return A new Global stack instance with the specified parameters.
    @classmethod
    def createGlobalStack(cls, new_stack_id: str, definition: DefinitionContainerInterface,
                          variant_container: "InstanceContainer",
                          material_container: "InstanceContainer",
                          quality_container: "InstanceContainer") -> GlobalStack:

        from cura.CuraApplication import CuraApplication
        application = CuraApplication.getInstance()
        registry = application.getContainerRegistry()

        stack = GlobalStack(new_stack_id)
        stack.setDefinition(definition)

        # Create user container
        user_container = cls.createUserChangesContainer(new_stack_id + "_user", definition.getId(), new_stack_id,
                                                        is_global_stack = True)

        stack.definitionChanges = cls.createDefinitionChangesContainer(stack, new_stack_id + "_settings")
        stack.variant = variant_container
        stack.material = material_container
        stack.quality = quality_container
        stack.qualityChanges = application.empty_quality_changes_container
        stack.userChanges = user_container

        registry.addContainer(user_container)

        return stack

    @classmethod
    def createUserChangesContainer(cls, container_name: str, definition_id: str, stack_id: str,
                                   is_global_stack: bool) -> "InstanceContainer":
        from cura.CuraApplication import CuraApplication
        application = CuraApplication.getInstance()
        registry = application.getContainerRegistry()

        unique_container_name = registry.uniqueName(container_name)

        container = InstanceContainer(unique_container_name)
        container.setDefinition(definition_id)
        container.setMetaDataEntry("type", "user")
        container.setMetaDataEntry("setting_version", CuraApplication.SettingVersion)

        metadata_key_to_add = "machine" if is_global_stack else "extruder"
        container.setMetaDataEntry(metadata_key_to_add, stack_id)

        return container

    @classmethod
    def createDefinitionChangesContainer(cls, container_stack, container_name):
        from cura.CuraApplication import CuraApplication
        application = CuraApplication.getInstance()
        registry = application.getContainerRegistry()

        unique_container_name = registry.uniqueName(container_name)

        definition_changes_container = InstanceContainer(unique_container_name)
        definition_changes_container.setDefinition(container_stack.getBottom().getId())
        definition_changes_container.setMetaDataEntry("type", "definition_changes")
        definition_changes_container.setMetaDataEntry("setting_version", CuraApplication.SettingVersion)

        registry.addContainer(definition_changes_container)
        container_stack.definitionChanges = definition_changes_container

        return definition_changes_container
