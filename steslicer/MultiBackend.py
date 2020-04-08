import argparse #To run the engine in debug mode if the front-end is in debug mode.
from collections import defaultdict
import os
from PyQt5.QtCore import QObject, QTimer, pyqtSlot
import sys
from time import time
from typing import Any, cast, Dict, List, Optional, Set, TYPE_CHECKING

from UM.Backend.Backend import Backend, BackendState
from UM.Scene.SceneNode import SceneNode
from UM.Signal import Signal
from UM.Logger import Logger
from UM.Message import Message
from UM.PluginRegistry import PluginRegistry
from UM.Resources import Resources
from UM.Platform import Platform
from UM.Qt.Duration import DurationFormat
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Settings.Interfaces import DefinitionContainerInterface
from UM.Settings.SettingInstance import SettingInstance #For typing.
from UM.Tool import Tool #For typing.
from UM.Mesh.MeshData import MeshData #For typing.

from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.Settings.ExtruderManager import ExtruderManager

import Arcus

if TYPE_CHECKING:
    from steslicer.Machines.Models.MultiBuildPlateModel import MultiBuildPlateModel
    from steslicer.Machines.MachineErrorChecker import MachineErrorChecker
    from UM.Scene.Scene import Scene
    from UM.Settings.ContainerStack import ContainerStack

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

class MultiBackend(QObject, Backend):
    def __init__(self):
        self._backends = {} #type: Dict[str, Backend]

    def addBackend(self, backend: Backend):
        pass

    def close(self):
        for backend_id, backend in self._backends:
            backend.close()