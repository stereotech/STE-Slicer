# Copyright (c) 2018 Ultimaker B.V.
# Uranium is released under the terms of the LGPLv3 or higher.

# The purpose of this class is to create fixtures or methods that can be shared among all settings tests.

import pytest

from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Settings.ContainerStack import setContainerRegistry
from UM.Settings.DefinitionContainer import DefinitionContainer #To provide definition containers in the registry fixtures.
from UM.Settings.InstanceContainer import InstanceContainer
from steslicer.Settings.SteSlicerContainerRegistry import SteSlicerContainerRegistry
from steslicer.Settings.ExtruderStack import ExtruderStack
from steslicer.Settings.GlobalStack import GlobalStack
import steslicer.Settings.SteSlicerContainerStack

# Returns the SteSlicerContainerRegistry instance with some empty containers.
@pytest.fixture()
def container_registry(application) -> SteSlicerContainerRegistry:
    ContainerRegistry._ContainerRegistry__instance= None    # Need to reset since we only allow one instance
    registry = SteSlicerContainerRegistry(application)
    setContainerRegistry(registry)
    return registry

# Gives an arbitrary definition container.
@pytest.fixture()
def definition_container() -> DefinitionContainer:
    return DefinitionContainer(container_id = "Test Definition")

# Gives an arbitrary definition changes container.
@pytest.fixture()
def definition_changes_container() -> InstanceContainer:
    definition_changes_container = InstanceContainer(container_id = "Test Definition Changes")
    definition_changes_container.setMetaDataEntry("type", "definition_changes")
    # Add current setting version to the instance container
    from steslicer.SteSlicerApplication import SteSlicerApplication
    definition_changes_container.getMetaData()["setting_version"] = SteSlicerApplication.SettingVersion
    return definition_changes_container

# An empty global stack to test with.
# There is a restriction here that the definition changes cannot be an empty container. Added in CURA-5281
@pytest.fixture()
def global_stack(definition_changes_container) -> GlobalStack:
    global_stack = GlobalStack("TestGlobalStack")
    global_stack._containers[steslicer.Settings.SteSlicerContainerStack._ContainerIndexes.DefinitionChanges] = definition_changes_container
    return global_stack

# An empty extruder stack to test with.
# There is a restriction here that the definition changes cannot be an empty container. Added in CURA-5281
@pytest.fixture()
def extruder_stack(definition_changes_container) -> ExtruderStack:
    extruder_stack= ExtruderStack("TestExtruderStack")
    extruder_stack._containers[steslicer.Settings.SteSlicerContainerStack._ContainerIndexes.DefinitionChanges] = definition_changes_container
    return extruder_stack