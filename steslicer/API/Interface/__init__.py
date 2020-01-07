# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from typing import TYPE_CHECKING

from UM.PluginRegistry import PluginRegistry
from steslicer.API.Interface.Settings import Settings

if TYPE_CHECKING:
    from steslicer.SteSlicerApplication import SteSlicerApplication


##  The Interface class serves as a common root for the specific API
#   methods for each interface element.
#
#   Usage:
#       ``from steslicer.API import CuraAPI
#       api = CuraAPI()
#       api.interface.settings.addContextMenuItem()
#       api.interface.viewport.addOverlay() # Not implemented, just a hypothetical
#       api.interface.toolbar.getToolButtonCount() # Not implemented, just a hypothetical
#       # etc.``

class Interface:

    # For now we use the same API version to be consistent.
    VERSION = PluginRegistry.APIVersion

    def __init__(self, application: "SteSlicerApplication") -> None:
        # API methods specific to the settings portion of the UI
        self.settings = Settings(application)