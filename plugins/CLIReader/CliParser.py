from cura.Scene.CuraSceneNode import CuraSceneNode

from UM.Logger import Logger
from cura.CuraApplication import CuraApplication
from cura.LayerDataBuilder import LayerDataBuilder
from cura.LayerDataDecorator import LayerDataDecorator
from cura.LayerPolygon import LayerPolygon
from cura.Scene.GCodeListDecorator import GCodeListDecorator
from cura.Settings.ExtruderManager import ExtruderManager
from UM.Settings.ContainerRegistry import ContainerRegistry

import numpy
import math
import re
from typing import Dict, List, NamedTuple, Optional, Union
from math import radians


class CliParser:

    def __init__(self) -> None:
        CuraApplication.getInstance().hideMessageSignal.connect(self._onHideMessage)
        self._cancelled = False
        self._message = None
        self._layer_number = 0
        self._extruder_number = 0
        self._clearValues()
        self._scene_node = None

        self._application = CuraApplication.getInstance()
        # stack to get print settingd via getProperty method
        self._global_stack = self._application.getGlobalContainerStack()
        self._filament_diameter = 1.75

    def processCliStream(self, stream: str) -> Optional[CuraSceneNode]:
        return None

    def _onHideMessage(self, message: str) -> None:
        if message == self._message:
            self._cancelled = True

    def _clearValues(self):
        pass
