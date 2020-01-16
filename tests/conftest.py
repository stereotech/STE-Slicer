

# The purpose of this class is to create fixtures or methods that can be shared among all tests.

import unittest.mock
import pytest

import Arcus #Prevents error: "PyCapsule_GetPointer called with incorrect name" with conflicting SIP configurations between Arcus and PyQt: Import Arcus and Savitar first!
import Savitar
from UM.Qt.QtApplication import QtApplication #QtApplication import is required, even though it isn't used.
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.MachineActionManager import MachineActionManager


# Create a CuraApplication object that will be shared among all tests. It needs to be initialized.
# Since we need to use it more that once, we create the application the first time and use its instance afterwards.
@pytest.fixture()
def application() -> SteSlicerApplication:
    app = unittest.mock.MagicMock()
    return app

# Returns a MachineActionManager instance.
@pytest.fixture()
def machine_action_manager(application) -> MachineActionManager:
    return MachineActionManager(application)
