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
#from .ProcessSlicedLayersJob import ProcessSlicedLayersJob
#from .StartSliceJob import StartSliceJob, StartJobResult

import Arcus

if TYPE_CHECKING:
    from steslicer.Machines.Models.MultiBuildPlateModel import MultiBuildPlateModel
    from steslicer.Machines.MachineErrorChecker import MachineErrorChecker
    from UM.Scene.Scene import Scene
    from UM.Settings.ContainerStack import ContainerStack

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

class CliParserBackend(QObject, Backend):
    backendError = Signal()

    def __init__(self) -> None:
        super().__init__()
        executable_name = "CliParser"
        if Platform.isWindows():
            executable_name += ".exe"
        default_engine_location = executable_name
        if os.path.exists(os.path.join(SteSlicerApplication.getInstallPrefix(), "bin", executable_name)):
            default_engine_location = os.path.join(SteSlicerApplication.getInstallPrefix(), "bin", executable_name)
        if hasattr(sys, "frozen"):
            default_engine_location = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), executable_name)
        if Platform.isLinux() and not default_engine_location:
            if not os.getenv("PATH"):
                raise OSError("There is something wrong with your Linux installation.")
            for pathdir in cast(str, os.getenv("PATH")).split(os.pathsep):
                execpath = os.path.join(pathdir, executable_name)
                if os.path.exists(execpath):
                    default_engine_location = execpath
                    break

        self._application = SteSlicerApplication.getInstance() #type: SteSlicerApplication
        self._multi_build_plate_model = None #type: Optional[MultiBuildPlateModel]
        self._machine_error_checker = None #type: Optional[MachineErrorChecker]

        if not default_engine_location:
            raise EnvironmentError("Could not find CliParser")

        Logger.log("i", "Found CliParser at: %s", default_engine_location)

        default_engine_location = os.path.abspath(default_engine_location)
        self._application.getPreferences().addPreference("cli_backend/location", default_engine_location)

        # Workaround to disable layer view processing if layer view is not active.
        self._layer_view_active = False #type: bool
        self._onActiveViewChanged()

        self._stored_optimized_layer_data = {} #type: Dict[int, List[Arcus.PythonMessage]] # key is build plate number, then arrays are stored until they go to the ProcessSlicesLayersJob

        self._scene = self._application.getController().getScene() #type: Scene
        self._scene.sceneChanged.connect(self._onSceneChanged)
