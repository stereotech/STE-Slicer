import os
import subprocess
import tempfile
from collections import defaultdict
from enum import IntEnum
from time import time
from typing import Optional, List, Any, Dict, Set

import Arcus
from Arcus import PythonMessage
from PyQt5.QtCore import QObject, QTimer, pyqtSlot
from UM.Backend.Backend import Backend, BackendState
from UM.Logger import Logger
from UM.Message import Message
from UM.Qt.Duration import DurationFormat
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Scene import Scene
from UM.Scene.SceneNode import SceneNode
from UM.Settings.ContainerStack import ContainerStack
from UM.Settings.SettingInstance import SettingInstance
from UM.Signal import Signal
from UM.Tool import Tool

from steslicer.Utils.GenerateBasementJob import GenerateBasementJob
from steslicer.Utils.ProcessCliJob import ProcessCliJob
from steslicer.Utils.ProcessSlicedLayersJob import ProcessSlicedLayersJob
from .StartSliceJob import StartSliceJob, StartJobResult
from steslicer.MultiBackend import MultiBackend
from steslicer.Settings.ExtruderManager import ExtruderManager
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.BackendManager.BackendManager import BackendManager

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

class BackendIndexes(IntEnum):
    Classic = 0
    Cylindrical = 1

class CylindricalBackend(QObject, MultiBackend):
    printDurationMessage = Signal()
    slicingStarted = Signal()
    slicingCancelled = Signal()
    backendError = Signal()

    def __init__(self):
        super().__init__()
        self._application = SteSlicerApplication.getInstance()
        self._multi_build_plate_model = None  # type: Optional[MultiBuildPlateModel]
        self._machine_error_checker = None  # type: Optional[MachineErrorChecker]
        self._backend_manager = self._application.getBackendManager() #type: BackendManager
        if self._backend_manager is None:
            Logger.log("e", "Failed to load BackendManager!")

        self._states = []
        # Workaround to disable layer view processing if layer view is not active.
        self._layer_view_active = False  # type: bool
        self._onActiveViewChanged()

        self._stored_layer_data = []
        self._stored_optimized_layer_data = {}

        self._scene = self._application.getController().getScene()  # type: Scene
        self._scene.sceneChanged.connect(self._onSceneChanged)

        self._global_container_stack = None  # type: Optional[ContainerStack]

        self._slice_messages = [] #type: List[Any]
        self._start_slice_job_build_plate = None  # type: Optional[int]
        self._start_slice_job = None #type: Optional[StartSliceJob]
        self._generate_basement_job = None
        self._slicing = False  # type: bool # Are we currently slicing?
        self._restart = False  # type: bool # Back-end is currently restarting?
        self._tool_active = False  # type: bool # If a tool is active, some tasks do not have to do anything
        self._always_restart = True  # type: bool # Always restart the engine when starting a new slice. Don't keep the process running. TODO: Fix engine statelessness.
        self._build_plates_to_be_sliced = []  # type: List[int] # what needs slicing?
        self._engine_is_fresh = True  # type: bool # Is the newly started engine used before or not?

        self._backend_log_max_lines = 20000  # type: int # Maximum number of lines to buffer
        self._error_message = None  # type: Optional[Message] # Pop-up message that shows errors.
        self._last_num_objects = defaultdict(
            int)  # type: Dict[int, int] # Count number of objects to see if there is something changed
        self._postponed_scene_change_sources = []  # type: List[SceneNode] # scene change is postponed (by a tool)
        self._process_layers_job = None
        self._process_cli_job = None
        self._slice_start_time = None  # type: Optional[float]
        self._is_disabled = False  # type: bool

        self._material_amounts = []
        self._times = {}

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
        self._loadBackends()

        self._multi_build_plate_model = self._application.getMultiBuildPlateModel()

        self._application.getController().activeViewChanged.connect(self._onActiveViewChanged)

        if self._multi_build_plate_model:
            self._multi_build_plate_model.activeBuildPlateChanged.connect(self._onActiveViewChanged)

        self._application.globalContainerStackChanged.connect(self._onGlobalStackChanged)
        self._onGlobalStackChanged()

        # extruder enable / disable. Actually wanted to use machine manager here, but the initialization order causes it to crash
        ExtruderManager.getInstance().extrudersChanged.connect(self._extruderChanged)

        # self.backendQuit.connect(self._onBackendQuit)
        # self.backendConnected.connect(self._onBackendConnected)

        # When a tool operation is in progress, don't slice. So we need to listen for tool operations.
        self._application.getController().toolOperationStarted.connect(self._onToolOperationStarted)
        self._application.getController().toolOperationStopped.connect(self._onToolOperationStopped)

        self._machine_error_checker = self._application.getMachineErrorChecker()
        self._machine_error_checker.errorCheckFinished.connect(self._onStackErrorCheckFinished)

    def _loadBackends(self) -> None:
        classic_backend = self._backend_manager.getBackendByType("classic")
        cylindrical_backend = self._backend_manager.getBackendByType("cylindrical")
        if classic_backend is None or cylindrical_backend is None:
            raise ModuleNotFoundError("Not all Backends found")
        self._states = [BackendState.NotStarted, BackendState.NotStarted]

        self.addBackend(classic_backend)
        self.addBackend(cylindrical_backend)

    def close(self) -> None:
        for backend in self.getBackends():  # type: Backend
            backend._terminate()

    @pyqtSlot()
    def stopSlicing(self) -> None:
        self.backendStateChange.emit(BackendState.NotStarted)
        if self._slicing:
            self.close()

        if self._generate_basement_job is not None:
            Logger.log("d", "Aborting generate basement job...")
            self._generate_basement_job.abort()
            self._generate_basement_job = None

        if self._process_cli_job is not None:
            Logger.log("d", "Aborting process cli job...")
            self._process_cli_job.abort()
            self._process_cli_job = None

        if self._process_layers_job is not None:
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
        self._material_amounts = []
        self._times = {}
        self._slice_start_time = time()
        if not self._build_plates_to_be_sliced:
            self.processingProgress.emit(1.0)
            Logger.log("w", "Slice unnecessary, nothing has changed that needs reslicing.")
            return

        if self._process_layers_job:
            Logger.log("d", "Process layers job still busy, trying later.")
            return

        if not hasattr(self._scene, "gcode_dict"):
            self._scene.gcode_dict = {} #type: ignore #Because we are creating the missing attribute here.

        # see if we really have to slice
        active_build_plate = self._application.getMultiBuildPlateModel().activeBuildPlate
        build_plate_to_be_sliced = self._build_plates_to_be_sliced.pop(0)
        Logger.log("d", "Going to slice build plate [%s]!" % build_plate_to_be_sliced)
        num_objects = self._numObjectsPerBuildPlate()

        self._stored_layer_data = []
        self._stored_optimized_layer_data[build_plate_to_be_sliced] = []

        if build_plate_to_be_sliced not in num_objects or num_objects[build_plate_to_be_sliced] == 0:
            self._scene.gcode_dict[build_plate_to_be_sliced] = []
            Logger.log("d", "Build plate %s has no objects to be sliced, skipping", build_plate_to_be_sliced)
            if self._build_plates_to_be_sliced:
                self.slice()
            return

        if self._application.getPrintInformation() and build_plate_to_be_sliced == active_build_plate:
            self._application.getPrintInformation().setToZeroPrintInformation(build_plate_to_be_sliced)

        self.stopSlicing()

        self.processingProgress.emit(0.0)
        self.backendStateChange.emit(BackendState.NotStarted)

        self._scene.gcode_dict[build_plate_to_be_sliced] = []
        self._slicing = True
        self.slicingStarted.emit()

        self.determineAutoSlicing()

        self._start_slice_job = StartSliceJob(self.getBackends())
        self._start_slice_job_build_plate = build_plate_to_be_sliced
        self._start_slice_job.setBuildPlate(self._start_slice_job_build_plate)
        self._start_slice_job.start()
        self._start_slice_job.finished.connect(self._onStartSliceCompleted)

    def _onStartSliceCompleted(self, job) -> None:
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
                                                            "Unable to slice with the current material as it is incompatible with the selected machine or configuration."),
                                              title=catalog.i18nc("@info:title", "Unable to slice"))
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
                self._error_message = Message(catalog.i18nc("@info:status",
                                                            "Unable to slice because the prime tower or prime position(s) are invalid."),
                                              title=catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)

        if job.getResult() == StartJobResult.ObjectsWithDisabledExtruder:
            self._error_message = Message(catalog.i18nc("@info:status",
                                                        "Unable to slice because there are objects associated with disabled Extruder %s." % job.getMessage()),
                                          title=catalog.i18nc("@info:title", "Unable to slice"))
            self._error_message.show()
            self.backendStateChange.emit(BackendState.Error)
            self.backendError.emit(job)
            return

        if job.getResult() == StartJobResult.NothingToSlice:
            if self._application.platformActivity:
                self._error_message = Message(catalog.i18nc("@info:status",
                                                            "Nothing to slice because none of the models fit the build volume. Please scale or rotate models to fit."),
                                              title=catalog.i18nc("@info:title", "Unable to slice"))
                self._error_message.show()
                self.backendStateChange.emit(BackendState.Error)
                self.backendError.emit(job)
            else:
                self.backendStateChange.emit(BackendState.NotStarted)
            self._invokeSlice()
            return

        self.backendStateChange.emit(BackendState.Processing)
        self._slice_messages = job.getSliceMessages()

        self._generate_basement_job = GenerateBasementJob()
        self._generate_basement_job.processingProgress.connect(self._onGenerateBasementProcessingProgress)
        self._generate_basement_job.finished.connect(self._onGenerateBasementJobFinished)
        self._generate_basement_job.start()

    def _onGenerateBasementProcessingProgress(self, amount):
        self.processingProgress.emit(amount / 10)
        self.backendStateChange.emit(BackendState.Processing)

    def _onGenerateBasementJobFinished(self, job: GenerateBasementJob):
        if not self._scene.gcode_dict:
            self._scene.gcode_dict = {0: []}
        if not self._scene.gcode_dict[self._start_slice_job_build_plate]:
            self._scene.gcode_dict[self._start_slice_job_build_plate] = []
        self._scene.gcode_dict[self._start_slice_job_build_plate].extend(job.getGCodeList())

        if self._start_slice_job_build_plate is not None:
            if self._start_slice_job_build_plate not in self._stored_optimized_layer_data:
                self._stored_optimized_layer_data[self._start_slice_job_build_plate] = []
        self._stored_optimized_layer_data[self._start_slice_job_build_plate].extend(job.getLayersData())

        if self._generate_basement_job is job:
            self._generate_basement_job = None
        # sending to the first backend
        for slice_message in self._slice_messages:
            if isinstance(slice_message, PythonMessage):
                self._backends["CuraEngineBackend"]._terminate()
                self._backends["CuraEngineBackend"]._createSocket()
                Logger.log("d", "Sending Arcus Message")
                # Listeners for receiving messages from the back-end.
                self._backends["CuraEngineBackend"]._message_handlers["cura.proto.Layer"] = self._onLayerMessage
                self._backends["CuraEngineBackend"]._message_handlers[
                    "cura.proto.LayerOptimized"] = self._onOptimizedLayerMessage
                self._backends["CuraEngineBackend"]._message_handlers["cura.proto.Progress"] = self._onProgressMessage
                self._backends["CuraEngineBackend"]._message_handlers[
                    "cura.proto.GCodeLayer"] = self._onGCodeLayerMessage
                self._backends["CuraEngineBackend"]._message_handlers[
                    "cura.proto.GCodePrefix"] = self._onGCodePrefixMessage
                self._backends["CuraEngineBackend"]._message_handlers[
                    "cura.proto.PrintTimeMaterialEstimates"] = self._onPrintTimeMaterialEstimates
                self._backends["CuraEngineBackend"]._message_handlers[
                    "cura.proto.SlicingFinished"] = self._onSlicingFinishedMessage
                self._backends["CuraEngineBackend"]._socket.sendMessage(slice_message)

    def _sendSliceMessage(self, slice_message):
        if isinstance(slice_message, List):
            Logger.log("d", "Sending Engine Message")
            slice_message.append('-o')
            output_path = os.path.join(tempfile.tempdir, next(tempfile._get_candidate_names()))
            slice_message.append(output_path)
            self._process = self._runEngineProcess(slice_message)
            self._startProcessCliLayersJob(output_path, self._application.getMultiBuildPlateModel().activeBuildPlate)
        if self._slice_start_time:
            Logger.log("d", "Sending slice message took %s seconds", time() - self._slice_start_time)

    def _onLayerMessage(self, message: Arcus.PythonMessage) -> None:
        self._stored_layer_data.append(message)

    def _onOptimizedLayerMessage(self, message: Arcus.PythonMessage) -> None:
        if self._start_slice_job_build_plate is not None:
            if self._start_slice_job_build_plate not in self._stored_optimized_layer_data:
                self._stored_optimized_layer_data[self._start_slice_job_build_plate] = []
            self._stored_optimized_layer_data[self._start_slice_job_build_plate].append(message)

    def _onProgressMessage(self, message: Arcus.PythonMessage) -> None:
        self.processingProgress.emit(0.1 + message.amount / 2.23)
        self.backendStateChange.emit(BackendState.Processing)

    def _onGCodeLayerMessage(self, message: Arcus.PythonMessage) -> None:
        if not self._scene.gcode_dict:
            self._scene.gcode_dict = {0: []}
        if not self._scene.gcode_dict[self._start_slice_job_build_plate]:
            self._scene.gcode_dict[self._start_slice_job_build_plate] = []
        msg = message.data.decode("utf-8", "replace") # type: str
        if msg.startswith(";Generated with Cura_SteamEngine"):
            msg = msg.replace("G55", "G56")
            self._scene.gcode_dict[self._start_slice_job_build_plate].insert(0, msg)
        else:
            self._scene.gcode_dict[self._start_slice_job_build_plate].append(msg) #type: ignore #Because we generate this attribute dynamically.

    def _onGCodePrefixMessage(self, message: Arcus.PythonMessage) -> None:
        if not self._scene.gcode_dict:
            self._scene.gcode_dict = {0: []}
        if not self._scene.gcode_dict[self._start_slice_job_build_plate]:
            self._scene.gcode_dict[self._start_slice_job_build_plate] = []
        self._scene.gcode_dict[self._start_slice_job_build_plate].insert(0, message.data.decode("utf-8",
                                                                                                "replace"))  # type: ignore #Because we generate this attribute dynamically.

    def _onPrintTimeMaterialEstimates(self, message: Arcus.PythonMessage) -> None:
        self._material_amounts = []
        for index in range(message.repeatedMessageCount("materialEstimates")):
            self._material_amounts.append(message.getRepeatedMessage("materialEstimates", index).material_amount)

        self._times = self._parseMessagePrintTimes(message)
        self.printDurationMessage.emit(self._start_slice_job_build_plate, self._times, self._material_amounts)

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

    def _onSlicingFinishedMessage(self, message: Arcus.PythonMessage) -> None:
        self.backendStateChange.emit(BackendState.Processing)
        self.processingProgress.emit(0.5)

        self._backends["CuraEngineBackend"]._message_handlers = {}

        gcode_list = self._scene.gcode_dict[self._start_slice_job_build_plate] #type: ignore #Because we generate this attribute dynamically.
        for index, line in enumerate(gcode_list):
            replaced = line.replace("{print_time}", str(self._application.getPrintInformation().currentPrintTime.getDisplayString(DurationFormat.Format.ISO8601)))
            replaced = replaced.replace("{filament_amount}", str(self._application.getPrintInformation().materialLengths))
            replaced = replaced.replace("{filament_weight}", str(self._application.getPrintInformation().materialWeights))
            replaced = replaced.replace("{filament_cost}", str(self._application.getPrintInformation().materialCosts))
            replaced = replaced.replace("{jobname}", str(self._application.getPrintInformation().jobName))

            gcode_list[index] = replaced

        # Launch GlicerBackend here
        for slice_message in self._slice_messages:
            self._sendSliceMessage(slice_message)

    def _runEngineProcess(self, command_list) -> Optional[subprocess.Popen]:
        try:
            return subprocess.Popen(command_list)
        except PermissionError:
            Logger.log("e", "Couldn't start back-end: No permission to execute process.")
        except FileNotFoundError:
            Logger.logException("e", "Unable to find backend executable: %s", command_list[0])
        return None

    def _startProcessCliLayersJob(self, output_path: str, build_plate_number: int) -> None:
        self._process_cli_job = ProcessCliJob(self._process, output_path)
        self._process_cli_job.setBuildPlate(build_plate_number)
        self._process_cli_job.finished.connect(self._onProcessCliFinished)
        # self._process_cli_job.processingCliGCodeParsed.connect(self._onProcessingCliGCodeParsed)
        # self._process_cli_job.processingCliLayersDataGenerated.connect(self._onProcessingCliLayersDataGenerated)
        self._process_cli_job.processingProgress.connect(self._onCliProgressMessage)
        # self._process_cli_job.timeMaterialEstimates.connect(self._onTimeMaterialEstimates)
        self._process_cli_job.start()

    def _onCliProgressMessage(self, amount) -> None:
        self.processingProgress.emit(0.55 + amount / 2.23)
        self.backendStateChange.emit(BackendState.Processing)


    def _onTimeMaterialEstimates(self, material_amounts, times):
        zipped_amounts = zip(self._material_amounts, material_amounts)
        # sum items in two lists
        self._material_amounts = [x + y for (x, y) in zipped_amounts]
        # and sum items in two dicts
        self._times = {k: self._times.get(k, 0) + times.get(k, 0) for k in set(self._times)}
        self.printDurationMessage.emit(self._start_slice_job_build_plate, self._times, self._material_amounts)

    def _onProcessCliFinished(self, job: ProcessCliJob):
        if job.isCancelled() or job.getError():
            self.backendStateChange.emit(BackendState.Error)
            self.backendError.emit(job)
            return

        if not self._scene.gcode_dict:
            self._scene.gcode_dict = {0: []}
        if not self._scene.gcode_dict[self._start_slice_job_build_plate]:
            self._scene.gcode_dict[self._start_slice_job_build_plate] = []
        # remove end gcode from Curaengine
        del self._scene.gcode_dict[self._start_slice_job_build_plate][-1]
        self._scene.gcode_dict[self._start_slice_job_build_plate].extend(job.getGCodeList())

        if self._start_slice_job_build_plate is not None:
            if self._start_slice_job_build_plate not in self._stored_optimized_layer_data:
                self._stored_optimized_layer_data[self._start_slice_job_build_plate] = []
            self._stored_optimized_layer_data[self._start_slice_job_build_plate].extend(job.getLayersData())

        self._onTimeMaterialEstimates(job.getMaterialAmounts(), job.getTimes())

        self.backendStateChange.emit(BackendState.Done)
        self.processingProgress.emit(1.0)

        self._slicing = False

        if self._process_cli_job is job:
            self._process_cli_job = None
        if self._slice_start_time:
            Logger.log("d", "Slicing took %s seconds", time() - self._slice_start_time)
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

    def _startProcessSlicedLayersJob(self, build_plate_number: int) -> None:
        self._process_layers_job = ProcessSlicedLayersJob(self._stored_optimized_layer_data[build_plate_number])
        self._process_layers_job.setBuildPlate(build_plate_number)
        self._process_layers_job.finished.connect(self._onProcessLayersFinished)
        self._process_layers_job.start()

    def _onProcessLayersFinished(self, job: ProcessSlicedLayersJob):
        del self._stored_optimized_layer_data[job.getBuildPlate()]
        self._process_layers_job = None
        Logger.log("d", "See if there is more to slice(2)...")
        self._invokeSlice()

    def _terminate(self) -> None:
        self._slicing = False
        self._stored_layer_data = []
        if self._start_slice_job_build_plate in self._stored_optimized_layer_data:
            del self._stored_optimized_layer_data[self._start_slice_job_build_plate]
        if self._start_slice_job is not None:
            self._start_slice_job.cancel()
        if self._application.getUseExternalBackend():
            return
        Logger.log("d", "Killing engine process")
        try:
            for backend in self.getBackends():  # type: Backend
                backend._terminate()
        except Exception as e:  # terminating a process that is already terminating causes an exception, silently ignore this.
            Logger.log("d", "Exception occurred while trying to kill the engine %s", str(e))

    ##  Called when the user changes the active view mode.
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

    def _onSceneChanged(self, source: SceneNode) -> None:
        if not isinstance(source, SceneNode):
            return
        if source.callDecoration("isBlockSlicing") and source.callDecoration("getLayerData"):
            self._stored_optimized_layer_data = {}

        build_plate_changed = set()
        source_build_plate_number = source.callDecoration("getBuildPlateNumber")
        if source == self._scene.getRoot():
            num_objects = self._numObjectsPerBuildPlate()
            for build_plate_number in list(self._last_num_objects.keys()) + list(num_objects.keys()):
                if build_plate_number not in self._last_num_objects or num_objects[build_plate_number] != \
                        self._last_num_objects[build_plate_number]:
                    self._last_num_objects[build_plate_number] = num_objects[build_plate_number]
                    build_plate_changed.add(build_plate_number)
        else:
            if not source.callDecoration("isGroup"):
                mesh_data = source.getMeshData()
                if mesh_data is None or mesh_data.getVertices() is None:
                    return

            if source_build_plate_number is not None:
                build_plate_changed.add(source_build_plate_number)

        if not build_plate_changed:
            return

        if self._tool_active:
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

    def determineAutoSlicing(self) -> bool:
        enable_timer = True
        self._is_disabled = False

        if not self._application.getPreferences().getValue("general/auto_slice"):
            enable_timer = False
        for node in DepthFirstIterator(
                self._scene.getRoot()):  # type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            if node.callDecoration("isBlockSlicing"):
                enable_timer = False
                self.backendStateChange.emit(BackendState.Disabled)
                self._is_disabled = True
            gcode_list = node.callDecoration("getGCodeList")
            if gcode_list is not None:
                self._scene.gcode_dict[node.callDecoration(
                    "getBuildPlateNumber")] = gcode_list  # type: ignore #Because we generate this attribute dynamically.

        if self._use_timer == enable_timer:
            return self._use_timer
        if enable_timer:
            self.backendStateChange.emit(BackendState.NotStarted)
            self.enableTimer()
            return True
        else:
            self.disableTimer()
            return False

    def _onPreferencesChanged(self, preference: str) -> None:
        if preference != "general/auto_slice":
            return
        auto_slice = self.determineAutoSlicing()
        if auto_slice:
            self._change_timer.start()

    def _extruderChanged(self) -> None:
        if not self._multi_build_plate_model:
            Logger.log("w", "GlicerBackend does not have multi_build_plate_model assigned!")
            return
        for build_plate_number in range(self._multi_build_plate_model.maxBuildPlate + 1):
            if build_plate_number not in self._build_plates_to_be_sliced:
                self._build_plates_to_be_sliced.append(build_plate_number)
        self._invokeSlice()

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
            self._global_container_stack.propertyChanged.connect(
                self._onSettingChanged)  # Note: Only starts slicing when the value changed.
            self._global_container_stack.containersChanged.connect(self._onChanged)
            extruders = list(self._global_container_stack.extruders.values())
            for extruder in extruders:
                extruder.propertyChanged.connect(self._onSettingChanged)
                extruder.containersChanged.connect(self._onChanged)
            self._onChanged()

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

    ##  Return a dict with number of objects per build plate
    def _numObjectsPerBuildPlate(self) -> Dict[int, int]:
        num_objects = defaultdict(int) #type: Dict[int, int]
        for node in DepthFirstIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            # Only count sliceable objects
            if node.callDecoration("isSliceable"):
                build_plate_number = node.callDecoration("getBuildPlateNumber")
                if build_plate_number is not None:
                    num_objects[build_plate_number] += 1
        return num_objects

    def _onSettingChanged(self, instance: SettingInstance, property: str) -> None:
        if property == "value":  # Only reslice if the value has changed.
            self.needsSlicing()
            self._onChanged()

        elif property == "validationState":
            if self._use_timer:
                self._change_timer.stop()

    def needsSlicing(self) -> None:
        self.stopSlicing()
        self.markSliceAll()
        self.processingProgress.emit(0.0)
        self.backendStateChange.emit(BackendState.NotStarted)
        if not self._use_timer:
            self._clearLayerData()

    def markSliceAll(self) -> None:
        for build_plate_number in range(self._application.getMultiBuildPlateModel().maxBuildPlate + 1):
            if build_plate_number not in self._build_plates_to_be_sliced:
                self._build_plates_to_be_sliced.append(build_plate_number)

    def _clearLayerData(self, build_plate_numbers: Set = None) -> None:
        self._scene.gcode_dict = {}
        for node in DepthFirstIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            if node.callDecoration("getLayerData"):
                if not build_plate_numbers or node.callDecoration("getBuildPlateNumber") in build_plate_numbers:
                    node.getParent().removeChild(node)

    def _onToolOperationStarted(self, tool: Tool) -> None:
        self._tool_active = True  # Do not react on scene change
        self.disableTimer()
        # Restart engine as soon as possible, we know we want to slice afterwards
        if not self._engine_is_fresh:
            self._terminate()

    def _onToolOperationStopped(self, tool: Tool) -> None:
        self._tool_active = False  # React on scene change again
        self.determineAutoSlicing()  # Switch timer on if appropriate
        # Process all the postponed scene changes
        while self._postponed_scene_change_sources:
            source = self._postponed_scene_change_sources.pop(0)
            self._onSceneChanged(source)

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

    def _onStackErrorCheckFinished(self) -> None:
        self.determineAutoSlicing()
        if self._is_disabled:
            return

        if not self._slicing and self._build_plates_to_be_sliced:
            self.needsSlicing()
            self._onChanged()

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

    def tickle(self) -> None:
        if self._use_timer:
            self._change_timer.start()

    def _createSocket(self, protocol_file):
        Logger.log("d", "Create Socket")
        pass
