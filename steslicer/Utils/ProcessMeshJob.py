import glob
from copy import deepcopy, copy

import numpy
from string import Formatter
from enum import IntEnum
import time
import trimesh
from trimesh.primitives import Box
from typing import Any, cast, Dict, List, Optional, Set
import re
import Arcus #For typing.

from UM.Job import Job
from UM.Logger import Logger
from UM.Mesh import MeshData
from UM.Scene.SceneNode import SceneNode
from UM.Settings.ContainerStack import ContainerStack #For typing.
from UM.Settings.SettingInstance import SettingInstance
from UM.Settings.SettingRelation import SettingRelation #For typing.

from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Scene import Scene #For typing.
from UM.Settings.Validator import ValidatorState
from UM.Settings.SettingRelation import RelationType

from plugins.CLIParserBackend.StartSliceJob import StartJobResult
from steslicer.Settings.SettingOverrideDecorator import SettingOverrideDecorator
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode
from steslicer.OneAtATimeIterator import OneAtATimeIterator
from steslicer.Settings.ExtruderManager import ExtruderManager
from steslicer.GcodeStartEndFormatter import GcodeStartEndFormatter

NON_PRINTING_MESH_SETTINGS = ["anti_overhang_mesh", "infill_mesh", "cutting_mesh"]

class ProcessMeshJob(Job):

    def __init__(self, process, output_path: List[str], slice_message: Arcus.PythonMessage):
        super().__init__()
        self._output_path = output_path #type: List[str]
        self._process = process #type: subprocess.Popen
        self._scene = SteSlicerApplication.getInstance().getController().getScene() #type: Scene
        self._global_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        self._slice_message = slice_message #type: Arcus.PythonMessage
        self._is_cancelled = False #type: bool
        self._build_plate_number = None #type: Optional[int]

        self._all_extruders_settings = None  # type: Optional[Dict[str, Any]] # cache for all setting values from all stacks (global & extruder) for the current machine

    def getSliceMessage(self) -> Arcus.PythonMessage:
        return self._slice_message

    def setBuildPlate(self, new_value):
        self._build_plate_number = new_value

    def cancel(self) -> None:
        super().cancel()
        self._is_cancelled = True

    def isCancelled(self) -> bool:
        return self._is_cancelled

    def setIsCancelled(self, value: bool):
        self._is_cancelled = value

    def run(self):
        while self._process.poll() is None:
            Job.yieldThread()
            if self._is_cancelled:
                return

        if self._build_plate_number is None:
            self.setResult(StartJobResult.Error)
            return
        object_list = self._slice_message.getRepeatedMessage("object_lists", 0)
        radius = self._global_stack.getProperty("spherical_mode_base_radius", "value")
        layer_height = self._global_stack.getProperty("layer_height", "value")
        layers_skip = int(radius // layer_height) + 2
        for index in range(len(self._output_path)):
            files = glob.glob(self._output_path[index] + "*" + ".stl")

            obj = object_list.getRepeatedMessage("objects", index)
            files = files[layers_skip:]
            for file_idx, filename in enumerate(files):
                if file_idx == 0:
                    obj.filename = filename
                else:
                    new_obj = object_list.addRepeatedMessage("objects")
                    new_obj.id = id(filename)
                    new_obj.name = obj.name + str(file_idx)
                    for setting_idx in range(obj.repeatedMessageCount("settings")):
                        obj_setting = obj.getRepeatedMessage("settings", setting_idx)
                        new_obj_setting = new_obj.addRepeatedMessage("settings")
                        new_obj_setting.name = obj_setting.name
                        new_obj_setting.value = obj_setting.value
                    new_obj.filename = filename
            #cli.filename = 'C:\\Users\\frylo\\AppData\\Local\\Temp\\test2_perimeterinflll.cli'

        self.setResult(StartJobResult.Finished)
