from copy import deepcopy, copy

import numpy
from string import Formatter
from enum import IntEnum
import time
import trimesh
from typing import Any, cast, Dict, List, Optional, Set
import re
import Arcus #For typing.
from UM.Backend.Backend import Backend

from UM.Job import Job
from UM.Logger import Logger
from UM.Mesh import MeshData
from UM.Message import Message
from UM.Scene.SceneNode import SceneNode
from UM.Settings.ContainerStack import ContainerStack #For typing.
from UM.Settings.SettingInstance import SettingInstance
from UM.Settings.SettingRelation import SettingRelation #For typing.

from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Scene import Scene #For typing.
from UM.Settings.Validator import ValidatorState
from UM.Settings.SettingRelation import RelationType

from plugins.CuraEngineBackend import CuraEngineBackend
from plugins.LayersProcessorBackend import LayersProcessorBackend
from steslicer.Settings.SettingOverrideDecorator import SettingOverrideDecorator
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode
from steslicer.OneAtATimeIterator import OneAtATimeIterator
from steslicer.Settings.ExtruderManager import ExtruderManager
from steslicer.GcodeStartEndFormatter import GcodeStartEndFormatter

class StartJobResult(IntEnum):
    Finished = 1
    Error = 2
    SettingError = 3
    NothingToSlice = 4
    MaterialIncompatible = 5
    BuildPlateError = 6
    ObjectSettingError = 7 #When an error occurs in per-object settings.
    ObjectsWithDisabledExtruder = 8

class StartSliceJob(Job):
    def __init__(self, backends: Dict[str, Backend]) -> None:
        super().__init__()
        self._backends = backends
        self._error_message = None  # type: Optional[Message] # Pop-up message that shows errors.
        self._start_slice_job_build_plate = None
        self._classic_start_slice_job = None #type: Optional[Job]
        self._spherical_start_slice_job = None
        self._slice_messages = []
        self._job_results = []
        self._is_cancelled = False  # type: bool

    def setBuildPlate(self, build_plate_number: int) -> None:
        self._start_slice_job_build_plate = build_plate_number

    def getSliceMessages(self) -> List[Any]:
        return self._slice_messages

    def cancel(self) -> None:
        super().cancel()
        self._is_cancelled = True

    def isCancelled(self) -> bool:
        return self._is_cancelled

    def setIsCancelled(self, value: bool):
        self._is_cancelled = value

    def run(self):
        if self._classic_start_slice_job:
            self._classic_start_slice_job = None
        self._slice_messages = []
        self._job_results = []
        classic_backend = self._backends["CuraEngineBackend"]
        slice_message = classic_backend._socket.createMessage("cura.proto.Slice")
        self._classic_start_slice_job = CuraEngineBackend.StartSliceJob(slice_message)
        self._classic_start_slice_job.setBuildPlate(self._start_slice_job_build_plate)
        self._classic_start_slice_job.start()
        while not self._classic_start_slice_job.isFinished():
            Job.yieldThread()
        Logger.log("d", "Classic start job finished with result: %s", self._classic_start_slice_job.getResult())
        self._job_results.append(self._classic_start_slice_job.getResult())
        if self._job_results[0] == StartJobResult.Finished:
            self._slice_messages.append(self._classic_start_slice_job.getSliceMessage())
        self._classic_start_slice_job = None

        spherical_backend = self._backends["LayersProcessorBackend"] #type: LayersProcessorBackend.LayersProcessorBackend
        slice_message = spherical_backend.getGlicerEngineCommand()
        arcus_message = spherical_backend._socket.createMessage("layersprocessor.proto.Slice")
        self._spherical_start_slice_job = LayersProcessorBackend.StartSliceJob(slice_message, arcus_message)
        self._spherical_start_slice_job.setBuildPlate(self._start_slice_job_build_plate)
        self._spherical_start_slice_job.start()
        while not self._spherical_start_slice_job.isFinished():
            Job.yieldThread()
        Logger.log("d", "Cylindrical start job finished with result: %s", self._spherical_start_slice_job.getResult())
        self._job_results.append(self._spherical_start_slice_job.getResult())
        if self._job_results[1] == StartJobResult.Finished:
            self._slice_messages.append(self._spherical_start_slice_job.getSliceMessage())
            self._slice_messages.append(self._spherical_start_slice_job.getArcusMessage())
        self._spherical_start_slice_job = None
        if any(result > 1 for result in self._job_results):
            self.setResult(max(self._job_results))
        else:
            self.setResult(StartJobResult.Finished)
