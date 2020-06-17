import argparse #To run the engine in debug mode if the front-end is in debug mode.
import subprocess
import tempfile
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

from steslicer.Utils.ProcessSlicedLayersJob import ProcessSlicedLayersJob
from .ProcessCliJob import ProcessCliJob
from .StartSliceJob import StartSliceJob, StartJobResult
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

        self._global_container_stack = None  # type: Optional[ContainerStack]

        self._start_slice_job = None  # type: Optional[StartSliceJob]
        self._process_cli_job = None # type: Optional[ProcessCliJob]
        self._start_slice_job_build_plate = None  # type: Optional[int]
        self._glicer_process = None
        self._slicing = False  # type: bool # Are we currently slicing?
        self._restart = False  # type: bool # Back-end is currently restarting?
        self._tool_active = False  # type: bool # If a tool is active, some tasks do not have to do anything
        self._always_restart = True  # type: bool # Always restart the engine when starting a new slice. Don't keep the process running. TODO: Fix engine statelessness.
        self._process_layers_job = None  # type: Optional[ProcessSlicedLayersJob] # The currently active job to process layers, or None if it is not processing layers.
        self._build_plates_to_be_sliced = []  # type: List[int] # what needs slicing?
        self._engine_is_fresh = True  # type: bool # Is the newly started engine used before or not?

        self._backend_log_max_lines = 20000  # type: int # Maximum number of lines to buffer
        self._error_message = None  # type: Optional[Message] # Pop-up message that shows errors.
        self._last_num_objects = defaultdict(
            int)  # type: Dict[int, int] # Count number of objects to see if there is something changed
        self._postponed_scene_change_sources = []  # type: List[SceneNode] # scene change is postponed (by a tool)

        self._slice_start_time = None  # type: Optional[float]
        self._is_disabled = False  # type: bool

        self._application.getPreferences().addPreference("general/auto_slice", False)

        self._use_timer = False  # type: bool
        # When you update a setting and other settings get changed through inheritance, many propertyChanged signals are fired.
        # This timer will group them up, and only slice for the last setting changed signal.
        # TODO: Properly group propertyChanged signals by whether they are triggered by the same user interaction.
        self._change_timer = QTimer()  # type: QTimer
        self._change_timer.setSingleShot(True)
        self._change_timer.setInterval(500)
        self.determineAutoSlicing()
        self._application.getPreferences().preferenceChanged.connect(self._onPreferencesChanged)

        self._application.initializationFinished.connect(self.initialize)

    def initialize(self) -> None:
        self._multi_build_plate_model = self._application.getMultiBuildPlateModel()

        self._application.getController().activeViewChanged.connect(self._onActiveViewChanged)

        if self._multi_build_plate_model:
            self._multi_build_plate_model.activeBuildPlateChanged.connect(self._onActiveViewChanged)

        self._application.globalContainerStackChanged.connect(self._onGlobalStackChanged)
        self._onGlobalStackChanged()

        # extruder enable / disable. Actually wanted to use machine manager here, but the initialization order causes it to crash
        ExtruderManager.getInstance().extrudersChanged.connect(self._extruderChanged)

        self.backendQuit.connect(self._onBackendQuit)
        self.backendConnected.connect(self._onBackendConnected)

        # When a tool operation is in progress, don't slice. So we need to listen for tool operations.
        self._application.getController().toolOperationStarted.connect(self._onToolOperationStarted)
        self._application.getController().toolOperationStopped.connect(self._onToolOperationStopped)

        self._machine_error_checker = self._application.getMachineErrorChecker()
        self._machine_error_checker.errorCheckFinished.connect(self._onStackErrorCheckFinished)

    def close(self) -> None:
        self._terminate()

    def getGlicerEngineCommand(self) -> List[str]:
        executable_name = "glicer_console.exe"
        default_engine_location = executable_name
        if os.path.exists(os.path.join(SteSlicerApplication.getInstallPrefix(), "bin", executable_name)):
            default_engine_location = os.path.join(SteSlicerApplication.getInstallPrefix(), "bin", executable_name)

        self._application = SteSlicerApplication.getInstance()  # type: SteSlicerApplication
        self._multi_build_plate_model = None  # type: Optional[MultiBuildPlateModel]
        self._machine_error_checker = None  # type: Optional[MachineErrorChecker]

        if not default_engine_location:
            raise EnvironmentError("Could not find Glicer")

        Logger.log("i", "Found Glicer at: %s", default_engine_location)
        default_engine_location = os.path.abspath(default_engine_location)
        return [default_engine_location]

    def getEngineCommand(self) -> List[str]:
        command = [self._application.getPreferences().getValue("cli_backend/location"), "connect", "127.0.0.1:{0}".format(self._port), ""]

        parser = argparse.ArgumentParser(prog = "steslicer", add_help = False)
        parser.add_argument("--debug", action = "store_true", default = False, help = "Turn on the debug mode by setting this option.")
        known_args = vars(parser.parse_known_args()[0])
        if known_args["debug"]:
            command.append("-vvv")

        return command

    printDurationMessage = Signal()
    slicingStarted = Signal()
    slicingCancelled = Signal()

    @pyqtSlot()
    def stopSlicing(self) -> None:
        self.backendStateChange.emit(BackendState.NotStarted)
        if self._slicing:  # We were already slicing. Stop the old job.
            self._terminate()
            self._createSocket()

        if self._process_layers_job is not None:  # We were processing layers. Stop that, the layers are going to change soon.
            Logger.log("d", "Aborting process layers job...")
            self._process_layers_job.abort()
            self._process_layers_job = None

        if self._error_message:
            self._error_message.hide()

    @pyqtSlot()
    def forceSlice(self) -> None:
        self.markSliceAll()
        self.slice()

    def slice(self) -> None:
        Logger.log("d", "Starting to slice...")
        self._slice_start_time = time()
        if not self._build_plates_to_be_sliced:
            self.processingProgress.emit(1.0)
            Logger.log("w", "Slice unnecessary, nothing has changed that needs reslicing.")
            return

        if self._process_layers_job:
            Logger.log("d", "Process layers job still busy, trying later.")
            return

        if not hasattr(self._scene, "gcode_dict"):
            self._scene.gcode_dict = {}  # type: ignore #Because we are creating the missing attribute here.

        # see if we really have to slice
        active_build_plate = self._application.getMultiBuildPlateModel().activeBuildPlate
        build_plate_to_be_sliced = self._build_plates_to_be_sliced.pop(0)
        Logger.log("d", "Going to slice build plate [%s]!" % build_plate_to_be_sliced)
        num_objects = self._numObjectsPerBuildPlate()

        self._stored_optimized_layer_data[build_plate_to_be_sliced] = []

        if build_plate_to_be_sliced not in num_objects or num_objects[build_plate_to_be_sliced] == 0:
            self._scene.gcode_dict[build_plate_to_be_sliced] = []
            Logger.log("d", "Build plate %s has no objects to be sliced, skipping", build_plate_to_be_sliced)
            if self._build_plates_to_be_sliced:
                self.slice()
            return

        if self._application.getPrintInformation() and build_plate_to_be_sliced == active_build_plate:
            self._application.getPrintInformation().setToZeroPrintInformation(build_plate_to_be_sliced)

        if self._process is None: # type: ignore
            self._createSocket()
        self.stopSlicing()
        self._engine_is_fresh = False  # Yes we're going to use the engine

        self.processingProgress.emit(0.0)
        self.backendStateChange.emit(BackendState.NotStarted)

        self._scene.gcode_dict[build_plate_to_be_sliced] = []
        self._slicing = True
        self.slicingStarted.emit()

        self.determineAutoSlicing()

        slice_message = self._socket.createMessage("cliparser.proto.Process")
        self._start_slice_job = StartSliceJob(self.getGlicerEngineCommand(), slice_message)
        self._start_slice_job_build_plate = build_plate_to_be_sliced
        self._start_slice_job.setBuildPlate(self._start_slice_job_build_plate)
        self._start_slice_job.start()

        self._start_slice_job.finished.connect(self._onStartSliceCompleted)

    def _terminate(self) -> None:
        self._slicing = False
        if self._start_slice_job_build_plate in self._stored_optimized_layer_data:
            del self._stored_optimized_layer_data[self._start_slice_job_build_plate]
        if self._start_slice_job is not None:
            self._start_slice_job.cancel()
        if self._process_cli_job is not None:
            self._process_cli_job.cancel()
        if self._application.getUseExternalBackend():
            return

        if self._glicer_process is not None: # type: ignore
            Logger.log("d", "Killing engine process")
            try:
                self._glicer_process.terminate() # type: ignore
                Logger.log("d", "Engine process is killed. Received return code %s", self._glicer_process.wait()) # type: ignore
                self._glicer_process = None # type: ignore
            except Exception as e:  # terminating a process that is already terminating causes an exception, silently ignore this.
                Logger.log("d", "Exception occurred while trying to kill the engine %s", str(e))

        Logger.log("d", "Attempting to kill the engine process")

        if self._application.getUseExternalBackend():
            return

        if self._process is not None:  # type: ignore
            Logger.log("d", "Killing engine process")
            try:
                self._process.terminate()  # type: ignore
                Logger.log("d", "Engine process is killed. Received return code %s",
                           self._process.wait())  # type: ignore
                self._process = None  # type: ignore

            except Exception as e:  # terminating a process that is already terminating causes an exception, silently ignore this.
                Logger.log("d", "Exception occurred while trying to kill the engine %s", str(e))

    def _onStartSliceCompleted(self, job: StartSliceJob) -> None:
        if self._error_message:
            self._error_message.hide()

        if self._start_slice_job is job:
            self._start_slice_job = None

        if job.isCancelled() or job.getError() or job.getResult() == StartJobResult.Error:
            self.backendStateChange.emit(BackendState.Error)
            self.backendError.emit(job)
            return

        if job.getResult() == StartJobResult.MaterialIncompatible:
            if self._application.platformActivity:
                self._error_message = Message(catalog.i18nc("@info:status",
                                            "Unable to slice with the current material as it is incompatible with the selected machine or configuration."), title = catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)
            return

        if job.getResult() == StartJobResult.SettingError:
            if self._application.platformActivity:
                if not self._global_container_stack:
                    Logger.log("w", "Global container stack not assigned to GlicerBackend!")
                    return

        if job.getResult() == StartJobResult.BuildPlateError:
            if self._application.platformActivity:
                self._error_message = Message(catalog.i18nc("@info:status", "Unable to slice because the prime tower or prime position(s) are invalid."),
                                              title = catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)

        if job.getResult() == StartJobResult.ObjectsWithDisabledExtruder:
            self._error_message = Message(catalog.i18nc("@info:status", "Unable to slice because there are objects associated with disabled Extruder %s." % job.getMessage()),
                                          title = catalog.i18nc("@info:title", "Unable to slice"))
            self._error_message.show()
            self.backendStateChange.emit(BackendState.Error)
            self.backendError.emit(job)
            return

        if job.getResult() == StartJobResult.NothingToSlice:
            if self._application.platformActivity:
                self._error_message = Message(catalog.i18nc("@info:status", "Nothing to slice because none of the models fit the build volume. Please scale or rotate models to fit."),
                                              title = catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)
            self._invokeSlice()
            return

        self.backendStateChange.emit(BackendState.Processing)
        slice_message = job.getSliceMessage()
        slice_message.append('-o')
        filename = next(tempfile._get_candidate_names())
        output_path = [os.path.join(tempfile.tempdir, filename + ".cli")]
        slice_message.extend(output_path)

        self._glicer_process = self._runGlicerEngineProcess(slice_message)
        # Notify the user that it's now up to the backend to do it's job
        arcus_message = job.getArcusMessage()
        self._startProcessCliLayersJob(output_path, self._application.getMultiBuildPlateModel().activeBuildPlate, arcus_message)

        Logger.log("i", "Started engine process: %s", self.getGlicerEngineCommand()[0])
        self._backendLog(bytes("Calling engine with: %s\n" % self.getGlicerEngineCommand(), "utf-8"))

        if self._slice_start_time:
            Logger.log("d", "Sending slice message took %s seconds", time() - self._slice_start_time)

    def _startProcessCliLayersJob(self, output_path: List[str], build_plate_number: int, arcus_message: Arcus.PythonMessage) -> None:
        self._process_cli_job = ProcessCliJob(self._glicer_process, output_path, arcus_message)
        self._process_cli_job.setBuildPlate(build_plate_number)
        self._process_cli_job.finished.connect(self._onProcessCliFinished)
        self._process_cli_job.start()

    def _runGlicerEngineProcess(self, command_list) -> Optional[subprocess.Popen]:
        try:
            return subprocess.Popen(command_list)
        except PermissionError:
            Logger.log("e", "Couldn't start back-end: No permission to execute process.")
        except FileNotFoundError:
            Logger.logException("e", "Unable to find backend executable: %s", command_list[0])
        return None

    def _onProcessCliFinished(self, job: ProcessCliJob):
        self._message_handlers["cliparser.proto.LayerOptimized"] = self._onOptimizedLayerMessage
        self._message_handlers["cliparser.proto.Progress"] = self._onProgressMessage
        self._message_handlers["cliparser.proto.GCodeLayer"] = self._onGCodeLayerMessage
        self._message_handlers["cliparser.proto.GCodePrefix"] = self._onGCodePrefixMessage
        self._message_handlers["cliparser.proto.PrintTimeMaterialEstimates"] = self._onPrintTimeMaterialEstimates
        self._message_handlers["cliparser.proto.SlicingFinished"] = self._onSlicingFinishedMessage

        if self._error_message:
            self._error_message.hide()

        # Note that cancelled slice jobs can still call this method.
        if self._process_cli_job is job:
            self._process_cli_job = None

        if job.isCancelled() or job.getError() or job.getResult() == StartJobResult.Error:
            self.backendStateChange.emit(BackendState.Error)
            self.backendError.emit(job)
            return

        if job.getResult() == StartJobResult.MaterialIncompatible:
            if self._application.platformActivity:
                self._error_message = Message(catalog.i18nc("@info:status",
                                            "Unable to slice with the current material as it is incompatible with the selected machine or configuration."), title = catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)
            return

        if job.getResult() == StartJobResult.SettingError:
            if self._application.platformActivity:
                if not self._global_container_stack:
                    Logger.log("w", "Global container stack not assigned to CuraEngineBackend!")
                    return
                extruders = ExtruderManager.getInstance().getActiveExtruderStacks()
                error_keys = [] #type: List[str]
                for extruder in extruders:
                    error_keys.extend(extruder.getErrorKeys())
                if not extruders:
                    error_keys = self._global_container_stack.getErrorKeys()
                error_labels = set()
                for key in error_keys:
                    for stack in [self._global_container_stack] + extruders: #Search all container stacks for the definition of this setting. Some are only in an extruder stack.
                        definitions = cast(DefinitionContainerInterface, stack.getBottom()).findDefinitions(key = key)
                        if definitions:
                            break #Found it! No need to continue search.
                    else: #No stack has a definition for this setting.
                        Logger.log("w", "When checking settings for errors, unable to find definition for key: {key}".format(key = key))
                        continue
                    error_labels.add(definitions[0].label)

                self._error_message = Message(catalog.i18nc("@info:status", "Unable to slice with the current settings. The following settings have errors: {0}").format(", ".join(error_labels)),
                                              title = catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)
            return

        elif job.getResult() == StartJobResult.ObjectSettingError:
            errors = {}
            for node in DepthFirstIterator(self._application.getController().getScene().getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                stack = node.callDecoration("getStack")
                if not stack:
                    continue
                for key in stack.getErrorKeys():
                    if not self._global_container_stack:
                        Logger.log("e", "CuraEngineBackend does not have global_container_stack assigned.")
                        continue
                    definition = cast(DefinitionContainerInterface, self._global_container_stack.getBottom()).findDefinitions(key = key)
                    if not definition:
                        Logger.log("e", "When checking settings for errors, unable to find definition for key {key} in per-object stack.".format(key = key))
                        continue
                    errors[key] = definition[0].label
            self._error_message = Message(catalog.i18nc("@info:status", "Unable to slice due to some per-model settings. The following settings have errors on one or more models: {error_labels}").format(error_labels = ", ".join(errors.values())),
                                          title = catalog.i18nc("@info:title", "Unable to slice"))
            self._error_message.show()
            self.backendStateChange.emit(BackendState.Error)
            self.backendError.emit(job)
            return

        if job.getResult() == StartJobResult.BuildPlateError:
            if self._application.platformActivity:
                self._error_message = Message(catalog.i18nc("@info:status", "Unable to slice because the prime tower or prime position(s) are invalid."),
                                              title = catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)

        if job.getResult() == StartJobResult.ObjectsWithDisabledExtruder:
            self._error_message = Message(catalog.i18nc("@info:status", "Unable to slice because there are objects associated with disabled Extruder %s." % job.getMessage()),
                                          title = catalog.i18nc("@info:title", "Unable to slice"))
            self._error_message.show()
            self.backendStateChange.emit(BackendState.Error)
            self.backendError.emit(job)
            return

        if job.getResult() == StartJobResult.NothingToSlice:
            if self._application.platformActivity:
                self._error_message = Message(catalog.i18nc("@info:status", "Nothing to slice because none of the models fit the build volume. Please scale or rotate models to fit."),
                                              title = catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)
            self._invokeSlice()
            return

        # Preparation completed, send it to the backend.
        self._socket.sendMessage(job.getSliceMessage())

        # Notify the user that it's now up to the backend to do it's job
        self.backendStateChange.emit(BackendState.Processing)
        self.processingProgress.emit(0.2)

        if self._slice_start_time:
            Logger.log("d", "Sending slice message took %s seconds", time() - self._slice_start_time )

    def determineAutoSlicing(self) -> bool:
        enable_timer = True
        self._is_disabled = False

        if not self._application.getPreferences().getValue("general/auto_slice"):
            enable_timer = False
        for node in DepthFirstIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            if node.callDecoration("isBlockSlicing"):
                enable_timer = False
                self.backendStateChange.emit(BackendState.Disabled)
                self._is_disabled = True
            gcode_list = node.callDecoration("getGCodeList")
            if gcode_list is not None:
                self._scene.gcode_dict[node.callDecoration("getBuildPlateNumber")] = gcode_list #type: ignore #Because we generate this attribute dynamically.

        if self._use_timer == enable_timer:
            return self._use_timer
        if enable_timer:
            self.backendStateChange.emit(BackendState.NotStarted)
            self.enableTimer()
            return True
        else:
            self.disableTimer()
            return False

    def _numObjectsPerBuildPlate(self) -> Dict[int, int]:
        num_objects = defaultdict(int) #type: Dict[int, int]
        for node in DepthFirstIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            # Only count sliceable objects
            if node.callDecoration("isSliceable"):
                build_plate_number = node.callDecoration("getBuildPlateNumber")
                if build_plate_number is not None:
                    num_objects[build_plate_number] += 1
        return num_objects

    def _onSceneChanged(self, source: SceneNode) -> None:
        if not isinstance(source, SceneNode):
            return

        # This case checks if the source node is a node that contains GCode. In this case the
        # current layer data is removed so the previous data is not rendered - CURA-4821
        if source.callDecoration("isBlockSlicing") and source.callDecoration("getLayerData"):
            self._stored_optimized_layer_data = {}

        build_plate_changed = set()
        source_build_plate_number = source.callDecoration("getBuildPlateNumber")
        if source == self._scene.getRoot():
            # we got the root node
            num_objects = self._numObjectsPerBuildPlate()
            for build_plate_number in list(self._last_num_objects.keys()) + list(num_objects.keys()):
                if build_plate_number not in self._last_num_objects or num_objects[build_plate_number] != self._last_num_objects[build_plate_number]:
                    self._last_num_objects[build_plate_number] = num_objects[build_plate_number]
                    build_plate_changed.add(build_plate_number)
        else:
            # we got a single scenenode
            if not source.callDecoration("isGroup"):
                mesh_data = source.getMeshData()
                if mesh_data is None or mesh_data.getVertices() is None:
                    return

            # There are some SceneNodes that do not have any build plate associated, then do not add to the list.
            if source_build_plate_number is not None:
                build_plate_changed.add(source_build_plate_number)

        if not build_plate_changed:
            return

        if self._tool_active:
            # do it later, each source only has to be done once
            if source not in self._postponed_scene_change_sources:
                self._postponed_scene_change_sources.append(source)
            return

        self.stopSlicing()
        for build_plate_number in build_plate_changed:
            if build_plate_number not in self._build_plates_to_be_sliced:
                self._build_plates_to_be_sliced.append(build_plate_number)
            self.printDurationMessage.emit(source_build_plate_number, {}, [])
        self.processingProgress.emit(0.0)
        self.backendStateChange.emit(BackendState.NotStarted)
        # if not self._use_timer:
            # With manually having to slice, we want to clear the old invalid layer data.
        self._clearLayerData(build_plate_changed)

        self._invokeSlice()

    def _onSocketError(self, error: Arcus.Error) -> None:
        if self._application.isShuttingDown():
            return

        super()._onSocketError(error)
        if error.getErrorCode() == Arcus.ErrorCode.Debug:
            return

        self._terminate()
        self._createSocket()

        if error.getErrorCode() not in [Arcus.ErrorCode.BindFailedError, Arcus.ErrorCode.ConnectionResetError, Arcus.ErrorCode.Debug]:
            Logger.log("w", "A socket error caused the connection to be reset")

        # _terminate()' function sets the job status to 'cancel', after reconnecting to another Port the job status
        # needs to be updated. Otherwise backendState is "Unable To Slice"
        if error.getErrorCode() == Arcus.ErrorCode.BindFailedError and self._start_slice_job is not None:
            self._start_slice_job.setIsCancelled(False)
        if error.getErrorCode() == Arcus.ErrorCode.BindFailedError and self._process_cli_job is not None:
            self._process_cli_job.setIsCancelled(False)

    def _clearLayerData(self, build_plate_numbers: Set = None) -> None:
        # Clear out any old gcode
        self._scene.gcode_dict = {}  # type: ignore

        for node in DepthFirstIterator(
                self._scene.getRoot()):  # type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            if node.callDecoration("getLayerData"):
                if not build_plate_numbers or node.callDecoration("getBuildPlateNumber") in build_plate_numbers:
                    node.getParent().removeChild(node)

    def markSliceAll(self) -> None:
        for build_plate_number in range(self._application.getMultiBuildPlateModel().maxBuildPlate + 1):
            if build_plate_number not in self._build_plates_to_be_sliced:
                self._build_plates_to_be_sliced.append(build_plate_number)

    def needsSlicing(self) -> None:
        self.stopSlicing()
        self.markSliceAll()
        self.processingProgress.emit(0.0)
        self.backendStateChange.emit(BackendState.NotStarted)
        if not self._use_timer:
            # With manually having to slice, we want to clear the old invalid layer data.
            self._clearLayerData()

    def _onSettingChanged(self, instance: SettingInstance, property: str) -> None:
        if instance == "printing_mode" and property == "value":
            self._message_handlers = {}

        if property == "value":  # Only reslice if the value has changed.
            self.needsSlicing()
            self._onChanged()

        elif property == "validationState":
            if self._use_timer:
                self._change_timer.stop()

    def _onStackErrorCheckFinished(self) -> None:
        self.determineAutoSlicing()
        if self._is_disabled:
            return

        if not self._slicing and self._build_plates_to_be_sliced:
            self.needsSlicing()
            self._onChanged()

    def _onOptimizedLayerMessage(self, message: Arcus.PythonMessage) -> None:
        if self._start_slice_job_build_plate is not None:
            if self._start_slice_job_build_plate not in self._stored_optimized_layer_data:
                self._stored_optimized_layer_data[self._start_slice_job_build_plate] = []
            self._stored_optimized_layer_data[self._start_slice_job_build_plate].append(message)

    def _onProgressMessage(self, message: Arcus.PythonMessage) -> None:
        self.processingProgress.emit(message.amount * 0.8 + 0.2)
        self.backendStateChange.emit(BackendState.Processing)

    def _invokeSlice(self) -> None:
        if self._use_timer:
            # if the error check is scheduled, wait for the error check finish signal to trigger auto-slice,
            # otherwise business as usual
            if self._machine_error_checker is None:
                self._change_timer.stop()
                return

            if self._machine_error_checker.needToWaitForResult:
                self._change_timer.stop()
            else:
                self._change_timer.start()

    def _onSlicingFinishedMessage(self, message: Arcus.PythonMessage) -> None:
        self.backendStateChange.emit(BackendState.Done)
        self.processingProgress.emit(1.0)

        gcode_list = self._scene.gcode_dict[self._start_slice_job_build_plate] #type: ignore #Because we generate this attribute dynamically.
        for index, line in enumerate(gcode_list):
            replaced = line.replace("{print_time}", str(self._application.getPrintInformation().currentPrintTime.getDisplayString(DurationFormat.Format.ISO8601)))
            replaced = replaced.replace("{filament_amount}", str(self._application.getPrintInformation().materialLengths))
            replaced = replaced.replace("{filament_weight}", str(self._application.getPrintInformation().materialWeights))
            replaced = replaced.replace("{filament_cost}", str(self._application.getPrintInformation().materialCosts))
            replaced = replaced.replace("{jobname}", str(self._application.getPrintInformation().jobName))

            gcode_list[index] = replaced


        if self._slice_start_time:
            Logger.log("d", "Slicing took %s seconds", time() - self._slice_start_time )
        Logger.log("d", "Number of models per buildplate: %s", dict(self._numObjectsPerBuildPlate()))

        # See if we need to process the sliced layers job.
        active_build_plate = self._application.getMultiBuildPlateModel().activeBuildPlate
        if (
            self._layer_view_active and
            (self._process_layers_job is None or not self._process_layers_job.isRunning()) and
            active_build_plate == self._start_slice_job_build_plate and
            active_build_plate not in self._build_plates_to_be_sliced):

            self._startProcessSlicedLayersJob(active_build_plate)
        # self._onActiveViewChanged()
        self._start_slice_job_build_plate = None

        Logger.log("d", "See if there is more to slice...")
        # Somehow this results in an Arcus Error
        # self.slice()
        # Call slice again using the timer, allowing the backend to restart
        if self._build_plates_to_be_sliced:
            self.enableTimer()  # manually enable timer to be able to invoke slice, also when in manual slice mode
            self._invokeSlice()
        self._message_handlers = {}
        self._slicing = False

    def _onGCodeLayerMessage(self, message: Arcus.PythonMessage) -> None:
        if not self._scene.gcode_dict:
            self._scene.gcode_dict = {0: []}
        if not self._scene.gcode_dict[self._start_slice_job_build_plate]:
            self._scene.gcode_dict[self._start_slice_job_build_plate] = []
        self._scene.gcode_dict[self._start_slice_job_build_plate].append(message.data.decode("utf-8", "replace")) #type: ignore #Because we generate this attribute dynamically.

    def _onGCodePrefixMessage(self, message: Arcus.PythonMessage) -> None:
        self._scene.gcode_dict[self._start_slice_job_build_plate].insert(0, message.data.decode("utf-8", "replace")) #type: ignore #Because we generate this attribute dynamically.

    ##  Creates a new socket connection.
    def _createSocket(self, protocol_file: str = None) -> None:
        if not protocol_file:
            plugin_path = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
            if not plugin_path:
                Logger.log("e", "Could not get plugin path!", self.getPluginId())
                return
            protocol_file = os.path.abspath(os.path.join(plugin_path, "CliParser.proto"))
        super()._createSocket(protocol_file)
        self._engine_is_fresh = True

    def _onChanged(self, *args: Any, **kwargs: Any) -> None:
        self.needsSlicing()
        if self._use_timer:
            # if the error check is scheduled, wait for the error check finish signal to trigger auto-slice,
            # otherwise business as usual
            if self._machine_error_checker is None:
                self._change_timer.stop()
                return

            if self._machine_error_checker.needToWaitForResult:
                self._change_timer.stop()
            else:
                self._change_timer.start()

    def _onPrintTimeMaterialEstimates(self, message: Arcus.PythonMessage) -> None:
        material_amounts = []
        for index in range(message.repeatedMessageCount("materialEstimates")):
            material_amounts.append(message.getRepeatedMessage("materialEstimates", index).material_amount)

        times = self._parseMessagePrintTimes(message)
        self.printDurationMessage.emit(self._start_slice_job_build_plate, times, material_amounts)

    def _parseMessagePrintTimes(self, message: Arcus.PythonMessage) -> Dict[str, float]:
        result = {
            "inset_0": message.time_inset_0,
            "inset_x": message.time_inset_x,
            "skin": message.time_skin,
            "infill": message.time_infill,
            "support_infill": message.time_support_infill,
            "support_interface": message.time_support_interface,
            "support": message.time_support,
            "skirt": message.time_skirt,
            "travel": message.time_travel,
            "retract": message.time_retract,
            "none": message.time_none
        }
        return result

    ##  Called when the back-end connects to the front-end.
    def _onBackendConnected(self) -> None:
        if not self._current:
            return
        if self._restart:
            self._restart = False
            self._onChanged()

    def _onToolOperationStarted(self, tool: Tool) -> None:
        self._tool_active = True  # Do not react on scene change
        self.disableTimer()
        # Restart engine as soon as possible, we know we want to slice afterwards
        if not self._engine_is_fresh:
            self._terminate()
            self._createSocket()

    def _onToolOperationStopped(self, tool: Tool) -> None:
        self._tool_active = False  # React on scene change again
        self.determineAutoSlicing()  # Switch timer on if appropriate
        # Process all the postponed scene changes
        while self._postponed_scene_change_sources:
            source = self._postponed_scene_change_sources.pop(0)
            self._onSceneChanged(source)

    def _startProcessSlicedLayersJob(self, build_plate_number: int) -> None:
        self._process_layers_job = ProcessSlicedLayersJob(self._stored_optimized_layer_data[build_plate_number])
        self._process_layers_job.setBuildPlate(build_plate_number)
        self._process_layers_job.finished.connect(self._onProcessLayersFinished)
        self._process_layers_job.start()

    def _onActiveViewChanged(self) -> None:
        view = self._application.getController().getActiveView()
        if view:
            active_build_plate = self._application.getMultiBuildPlateModel().activeBuildPlate
            if view.getPluginId() == "SimulationView":  # If switching to layer view, we should process the layers if that hasn't been done yet.
                self._layer_view_active = True
                # There is data and we're not slicing at the moment
                # if we are slicing, there is no need to re-calculate the data as it will be invalid in a moment.
                # TODO: what build plate I am slicing
                if (active_build_plate in self._stored_optimized_layer_data and
                    not self._slicing and
                    not self._process_layers_job and
                    active_build_plate not in self._build_plates_to_be_sliced):

                    self._startProcessSlicedLayersJob(active_build_plate)
            else:
                self._layer_view_active = False

    def _onBackendQuit(self) -> None:
        if not self._current:
            return
        if not self._restart:
            if self._glicer_process: # type: ignore
                Logger.log("d", "Backend quit with return code %s. Resetting process and socket.", self._glicer_process.wait()) # type: ignore
                self._glicer_process = None # type: ignore
            if self._process: # type: ignore
                Logger.log("d", "Backend quit with return code %s. Resetting process and socket.", self._process.wait()) # type: ignore
                self._process = None # type: ignore

    ##  Called when the global container stack changes
    def _onGlobalStackChanged(self) -> None:
        if self._global_container_stack:
            self._global_container_stack.propertyChanged.disconnect(self._onSettingChanged)
            self._global_container_stack.containersChanged.disconnect(self._onChanged)
            extruders = list(self._global_container_stack.extruders.values())

            for extruder in extruders:
                extruder.propertyChanged.disconnect(self._onSettingChanged)
                extruder.containersChanged.disconnect(self._onChanged)

        self._global_container_stack = self._application.getGlobalContainerStack()

        if self._global_container_stack:
            self._global_container_stack.propertyChanged.connect(self._onSettingChanged)  # Note: Only starts slicing when the value changed.
            self._global_container_stack.containersChanged.connect(self._onChanged)
            extruders = list(self._global_container_stack.extruders.values())
            for extruder in extruders:
                extruder.propertyChanged.connect(self._onSettingChanged)
                extruder.containersChanged.connect(self._onChanged)
            self._onChanged()

    def _onProcessLayersFinished(self, job: ProcessSlicedLayersJob) -> None:
        del self._stored_optimized_layer_data[job.getBuildPlate()]
        self._process_layers_job = None
        Logger.log("d", "See if there is more to slice(2)...")
        self._invokeSlice()

    ##  Connect slice function to timer.
    def enableTimer(self) -> None:
        if not self._use_timer:
            self._change_timer.timeout.connect(self.slice)
            self._use_timer = True

    ##  Disconnect slice function from timer.
    #   This means that slicing will not be triggered automatically
    def disableTimer(self) -> None:
        if self._use_timer:
            self._use_timer = False
            self._change_timer.timeout.disconnect(self.slice)

    def _onPreferencesChanged(self, preference: str) -> None:
        if preference != "general/auto_slice":
            return
        auto_slice = self.determineAutoSlicing()
        if auto_slice:
            self._change_timer.start()

    ##   Tickle the backend so in case of auto slicing, it starts the timer.
    def tickle(self) -> None:
        if self._use_timer:
            self._change_timer.start()

    def _extruderChanged(self) -> None:
        if not self._multi_build_plate_model:
            Logger.log("w", "CuraEngineBackend does not have multi_build_plate_model assigned!")
            return
        for build_plate_number in range(self._multi_build_plate_model.maxBuildPlate + 1):
            if build_plate_number not in self._build_plates_to_be_sliced:
                self._build_plates_to_be_sliced.append(build_plate_number)
        self._invokeSlice()
