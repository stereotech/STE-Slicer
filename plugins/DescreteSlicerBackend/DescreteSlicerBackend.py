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
from .ProcessSlicedLayersJob import ProcessSlicedLayersJob
from .StartSliceJob import StartSliceJob, StartJobResult

import Arcus

if TYPE_CHECKING:
    from steslicer.Machines.Models.MultiBuildPlateModel import MultiBuildPlateModel
    from steslicer.Machines.MachineErrorChecker import MachineErrorChecker
    from UM.Scene.Scene import Scene
    from UM.Settings.ContainerStack import ContainerStack

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

class DescreteSlicerBackend(QObject, Backend):
    backendError = Signal()

    def __init__(self) -> None:
        super().__init__()
        # Find out where the engine is located, and how it is called.
        # This depends on how Cura is packaged and which OS we are running on.
        executable_name = "DescreteSlicer"
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
            raise EnvironmentError("Could not find CuraEngine")

        Logger.log("i", "Found CuraEngine at: %s", default_engine_location)

        default_engine_location = os.path.abspath(default_engine_location)
        self._application.getPreferences().addPreference("backend/location", default_engine_location)

        # Workaround to disable layer view processing if layer view is not active.
        self._layer_view_active = False #type: bool
        self._onActiveViewChanged()

        self._stored_layer_data = [] #type: List[Arcus.PythonMessage]
        self._stored_optimized_layer_data = {} #type: Dict[int, List[Arcus.PythonMessage]] # key is build plate number, then arrays are stored until they go to the ProcessSlicesLayersJob

        self._scene = self._application.getController().getScene() #type: Scene
        self._scene.sceneChanged.connect(self._onSceneChanged)

        # Triggers for auto-slicing. Auto-slicing is triggered as follows:
        #  - auto-slicing is started with a timer
        #  - whenever there is a value change, we start the timer
        #  - sometimes an error check can get scheduled for a value change, in that case, we ONLY want to start the
        #    auto-slicing timer when that error check is finished
        # If there is an error check, stop the auto-slicing timer, and only wait for the error check to be finished
        # to start the auto-slicing timer again.
        #
        self._global_container_stack = None #type: Optional[ContainerStack]

        # Listeners for receiving messages from the back-end.
        #self._message_handlers["cura.proto.Layer"] = self._onLayerMessage
        #self._message_handlers["cura.proto.LayerOptimized"] = self._onOptimizedLayerMessage
        #self._message_handlers["cura.proto.Progress"] = self._onProgressMessage
        #self._message_handlers["cura.proto.GCodeLayer"] = self._onGCodeLayerMessage
        #self._message_handlers["cura.proto.GCodePrefix"] = self._onGCodePrefixMessage
        #self._message_handlers["cura.proto.PrintTimeMaterialEstimates"] = self._onPrintTimeMaterialEstimates
        #self._message_handlers["cura.proto.SlicingFinished"] = self._onSlicingFinishedMessage

        self._start_slice_job = None #type: Optional[StartSliceJob]
        self._start_slice_job_build_plate = None #type: Optional[int]
        self._slicing = False #type: bool # Are we currently slicing?
        self._restart = False #type: bool # Back-end is currently restarting?
        self._tool_active = False #type: bool # If a tool is active, some tasks do not have to do anything
        self._always_restart = True #type: bool # Always restart the engine when starting a new slice. Don't keep the process running. TODO: Fix engine statelessness.
        self._process_layers_job = None #type: Optional[ProcessSlicedLayersJob] # The currently active job to process layers, or None if it is not processing layers.
        self._build_plates_to_be_sliced = [] #type: List[int] # what needs slicing?
        self._engine_is_fresh = True #type: bool # Is the newly started engine used before or not?

        self._backend_log_max_lines = 20000 #type: int # Maximum number of lines to buffer
        self._error_message = None #type: Optional[Message] # Pop-up message that shows errors.
        self._last_num_objects = defaultdict(int) #type: Dict[int, int] # Count number of objects to see if there is something changed
        self._postponed_scene_change_sources = [] #type: List[SceneNode] # scene change is postponed (by a tool)

        self._slice_start_time = None #type: Optional[float]
        self._is_disabled = False #type: bool

        self._application.getPreferences().addPreference("general/auto_slice", False)

        self._use_timer = False #type: bool
        # When you update a setting and other settings get changed through inheritance, many propertyChanged signals are fired.
        # This timer will group them up, and only slice for the last setting changed signal.
        # TODO: Properly group propertyChanged signals by whether they are triggered by the same user interaction.
        self._change_timer = QTimer() #type: QTimer
        self._change_timer.setSingleShot(True)
        self._change_timer.setInterval(500)
        self.determineAutoSlicing()
        self._application.getPreferences().preferenceChanged.connect(self._onPreferencesChanged)

        self._application.initializationFinished.connect(self.initialize)
