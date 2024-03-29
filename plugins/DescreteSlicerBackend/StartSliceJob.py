import math
from copy import deepcopy, copy

import numpy
from string import Formatter
from enum import IntEnum
import time
import trimesh
from UM.Math.Matrix import Matrix
from UM.Math.Quaternion import Quaternion
from UM.Math.Vector import Vector
from UM.Mesh.MeshBuilder import MeshBuilder
from trimesh.primitives import Box
import trimesh.intersections
from typing import Any, cast, Dict, List, Optional, Set, NamedTuple
import re
import Arcus  # For typing.

from UM.Job import Job
from UM.Logger import Logger
from UM.Mesh import MeshData
from UM.Scene.SceneNode import SceneNode
from UM.Settings.ContainerStack import ContainerStack  # For typing.
from UM.Settings.SettingInstance import SettingInstance
from UM.Settings.SettingRelation import SettingRelation  # For typing.

from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Scene import Scene  # For typing.
from UM.Settings.Validator import ValidatorState
from UM.Settings.SettingRelation import RelationType

from steslicer.Scene.SplittingPlaneDecorator import SplittingPlaneDecorator
from steslicer.Settings.SettingOverrideDecorator import SettingOverrideDecorator
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode
from steslicer.OneAtATimeIterator import OneAtATimeIterator
from steslicer.Settings.ExtruderManager import ExtruderManager
from steslicer.GcodeStartEndFormatter import GcodeStartEndFormatter
from steslicer.Utils.SplitPlane import SplitByPlane

NON_PRINTING_MESH_SETTINGS = [
    "anti_overhang_mesh", "infill_mesh", "cutting_mesh"]


class StartJobResult(IntEnum):
    Finished = 1
    Error = 2
    SettingError = 3
    NothingToSlice = 4
    MaterialIncompatible = 5
    BuildPlateError = 6
    ObjectSettingError = 7  # When an error occurs in per-object settings.
    ObjectsWithDisabledExtruder = 8


# Job class that builds up the message of scene data to send to CuraEngine.
SplitPlane = NamedTuple("SplitPlane", [("normal", Any), ("origin", Any)])

class StartSliceJob(Job):
    def __init__(self, slice_message: Arcus.PythonMessage) -> None:
        super().__init__()

        self._scene = SteSlicerApplication.getInstance(
        ).getController().getScene()  # type: Scene
        self._slice_message = slice_message  # type: Arcus.PythonMessage
        self._is_cancelled = False  # type: bool
        self._build_plate_number = None  # type: Optional[int]

        # type: Optional[Dict[str, Any]] # cache for all setting values from all stacks (global & extruder) for the current machine
        self._all_extruders_settings = None
        self._direction_matrices = {}  # type: Dict[int, str]

    def getSliceMessage(self) -> Arcus.PythonMessage:
        return self._slice_message

    def setBuildPlate(self, build_plate_number: int) -> None:
        self._build_plate_number = build_plate_number

    # Check if a stack has any errors.
    # returns true if it has errors, false otherwise.
    def _checkStackForErrors(self, stack: ContainerStack) -> bool:
        if stack is None:
            return False

        for key in stack.getAllKeys():
            validation_state = stack.getProperty(key, "validationState")
            if validation_state in (ValidatorState.Exception, ValidatorState.MaximumError, ValidatorState.MinimumError):
                Logger.log(
                    "w", "Setting %s is not valid, but %s. Aborting slicing.", key, validation_state)
                return True
            Job.yieldThread()
        return False

    # Runs the job that initiates the slicing.
    def run(self) -> None:
        if self._build_plate_number is None:
            self.setResult(StartJobResult.Error)
            return

        stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        if not stack:
            self.setResult(StartJobResult.Error)
            return

        # Don't slice if there is a setting with an error value.
        if SteSlicerApplication.getInstance().getMachineManager().stacksHaveErrors:
            self.setResult(StartJobResult.SettingError)
            return

        if SteSlicerApplication.getInstance().getBuildVolume().hasErrors():
            self.setResult(StartJobResult.BuildPlateError)
            return

        # Don't slice if the buildplate or the nozzle type is incompatible with the materials
        if not SteSlicerApplication.getInstance().getMachineManager().variantBuildplateCompatible and \
                not SteSlicerApplication.getInstance().getMachineManager().variantBuildplateUsable:
            self.setResult(StartJobResult.MaterialIncompatible)
            return

        for position, extruder_stack in stack.extruders.items():
            material = extruder_stack.findContainer({"type": "material"})
            if not extruder_stack.isEnabled:
                continue
            if material:
                if material.getMetaDataEntry("compatible") == False:
                    self.setResult(StartJobResult.MaterialIncompatible)
                    return

        # Don't slice if there is a per object setting with an error value.
        # type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
        for node in DepthFirstIterator(self._scene.getRoot()):
            if not isinstance(node, SteSlicerSceneNode) or not node.isSelectable():
                continue

            if self._checkStackForErrors(node.callDecoration("getStack")):
                self.setResult(StartJobResult.ObjectSettingError)
                return

        with self._scene.getSceneLock():
            # Remove old layer data.
            # type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            for node in DepthFirstIterator(self._scene.getRoot()):
                if node.callDecoration("getLayerData") and node.callDecoration(
                        "getBuildPlateNumber") == self._build_plate_number:
                    node.getParent().removeChild(node)
                    break

            # Get the objects in their groups to print.
            object_groups = []
            printing_mode = stack.getProperty("printing_mode", "value")
            if printing_mode == "discrete":
                if stack.getProperty("print_sequence", "value") == "one_at_a_time":
                    # type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                    for node in OneAtATimeIterator(self._scene.getRoot()):
                        temp_list = []

                        # Node can't be printed, so don't bother sending it.
                        if getattr(node, "_outside_buildarea", False):
                            continue

                        # Filter on current build plate
                        build_plate_number = node.callDecoration(
                            "getBuildPlateNumber")
                        if build_plate_number is not None and build_plate_number != self._build_plate_number:
                            continue

                        children = node.getAllChildren()
                        children.append(node)
                        for child_node in children:
                            if child_node.getMeshData() and child_node.getMeshData().getVertices() is not None:
                                temp_list.append(child_node)

                        if temp_list:
                            object_groups.append(temp_list)
                        Job.yieldThread()
                    if len(object_groups) == 0:
                        Logger.log(
                            "w", "No objects suitable for one at a time found, or no correct order found")
                else:
                    temp_list = []
                    has_printing_mesh = False
                    # type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                    for node in DepthFirstIterator(self._scene.getRoot()):
                        if node.callDecoration(
                                "isSliceable") and node.getMeshData() and node.getMeshData().getVertices() is not None:
                            per_object_stack = node.callDecoration("getStack")
                            is_non_printing_mesh = False
                            if per_object_stack:
                                is_non_printing_mesh = any(per_object_stack.getProperty(
                                    key, "value") for key in NON_PRINTING_MESH_SETTINGS)

                            # Find a reason not to add the node
                            if node.callDecoration("getBuildPlateNumber") != self._build_plate_number:
                                continue
                            if getattr(node, "_outside_buildarea", False) and not is_non_printing_mesh:
                                continue

                            temp_list.append(node)
                            if not is_non_printing_mesh:
                                has_printing_mesh = True

                        Job.yieldThread()

                    # If the list doesn't have any model with suitable settings then clean the list
                    # otherwise CuraEngine will crash
                    if not has_printing_mesh:
                        temp_list.clear()

                    if temp_list:
                        object_groups.append(temp_list)
            else:
                self.setResult(StartJobResult.ObjectSettingError)
                return

        global_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        if not global_stack:
            return
        extruders_enabled = {
            position: stack.isEnabled for position, stack in global_stack.extruders.items()}
        filtered_object_groups = []
        has_model_with_disabled_extruders = False
        associated_disabled_extruders = set()
        for group in object_groups:
            stack = global_stack
            skip_group = False
            for node in group:
                # Only check if the printing extruder is enabled for printing meshes
                is_non_printing_mesh = node.callDecoration(
                    "evaluateIsNonPrintingMesh")
                extruder_position = node.callDecoration(
                    "getActiveExtruderPosition")
                if not is_non_printing_mesh and not extruders_enabled[extruder_position]:
                    skip_group = True
                    has_model_with_disabled_extruders = True
                    associated_disabled_extruders.add(extruder_position)
            if not skip_group:
                filtered_object_groups.append(group)

        if has_model_with_disabled_extruders:
            self.setResult(StartJobResult.ObjectsWithDisabledExtruder)
            associated_disabled_extruders = {str(c) for c in sorted(
                [int(p) + 1 for p in associated_disabled_extruders])}
            self.setMessage(", ".join(associated_disabled_extruders))
            return

        # There are cases when there is nothing to slice. This can happen due to one at a time slicing not being
        # able to find a possible sequence or because there are no objects on the build plate (or they are outside
        # the build volume)
        if not filtered_object_groups:
            self.setResult(StartJobResult.NothingToSlice)
            return

        cancelled = self._is_cancelled
        self._is_cancelled = False

        processed_object_groups = []
        for object_group in filtered_object_groups:
            printable_meshes = []
            splitting_planes = []
            for object in object_group:
                per_object_stack = object.callDecoration("getStack")
                settings = per_object_stack.getTop()
                anti_overhang_mesh = settings.getProperty(
                    "anti_overhang_mesh", "value")
                splitting_plane = object.callDecoration("isSplittingPlane")
                if anti_overhang_mesh and splitting_plane:
                    splitting_planes.append(object)
                elif not anti_overhang_mesh:
                    printable_meshes.append(object)

            for mesh in printable_meshes:
                processed_nodes = self.generateSplitTree(mesh, splitting_planes)
                for child in reversed(processed_nodes):
                    processed_object_groups.append([child])

        self._buildGlobalSettingsMessage(stack)
        self._buildGlobalInheritsStackMessage(stack)

        # Build messages for extruder stacks
        # Send the extruder settings in the order of extruder positions. Somehow, if you send e.g. extruder 3 first,
        # then CuraEngine can slice with the wrong settings. This I think should be fixed in CuraEngine as well.
        extruder_stack_list = sorted(
            list(global_stack.extruders.items()), key=lambda item: int(item[0]))
        for _, extruder_stack in extruder_stack_list:
            self._buildExtruderMessage(extruder_stack)

        for group in processed_object_groups:
            group_message = self._slice_message.addRepeatedMessage(
                "object_lists")
            if group[0].getParent() is not None and group[0].getParent().callDecoration("isGroup"):
                self._handlePerObjectSettings(
                    group[0].getParent(), group_message)
            for object in group:
                mesh_data = object.getMeshData()
                rot_scale = object.getWorldTransformation().getTransposed().getData()[
                            0:3, 0:3]
                translate = object.getWorldTransformation().getData()[:3, 3]

                # This effectively performs a limited form of MeshData.getTransformed that ignores normals.
                verts = mesh_data.getVertices()
                verts = verts.dot(rot_scale)
                verts += translate

                # Convert from Y up axes to Z up axes. Equals a 90 degree rotation.
                verts[:, [1, 2]] = verts[:, [2, 1]]
                verts[:, 1] *= -1

                obj = group_message.addRepeatedMessage("objects")
                obj.id = id(object)
                obj.name = object.getName()
                indices = mesh_data.getIndices()
                if indices is not None:
                    flat_verts = numpy.take(verts, indices.flatten(), axis=0)
                else:
                    flat_verts = numpy.array(verts)

                obj.vertices = flat_verts

                self._handlePerObjectSettings(object, obj)

                Job.yieldThread()

        self.setResult(StartJobResult.Finished)

    def generateSplitTree(self, node: SceneNode, planes: List[SceneNode]):
        result = []
        new_node = copy(node)
        new_nodes = [new_node]
        global_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        if not global_stack:
            return result
        overlap = global_stack.getProperty("descrete_mode_parts_intersection", "value")
        converted_planes = self.convertPlanes(planes)
        for plane_idx, plane in reversed(list(enumerate(converted_planes))):
            new_nodes = self.splitNode(new_node, plane, overlap)
            new_node = new_nodes[0]
            if len(new_nodes) > 1:
                result.append(new_nodes[-1])
        result.append(new_node)
        return result

    def convertPlanes(self, planes: List[SceneNode]) -> List[SplitPlane]:
        ret = []
        for plane in planes:
            plane_mesh_data = plane.getMeshDataTransformed()
            plane_normal = plane_mesh_data.getNormals()[0]
            plane_origin = plane_mesh_data.getVertices()[0] + 0.5 * (plane_mesh_data.getVertices()[2] - plane_mesh_data.getVertices()[0])
            new_plane = SplitPlane(plane_normal, plane_origin)
            ret.append(new_plane)
        ret = self.addItermediatePlanes(ret)
        return ret

    def addItermediatePlanes(self, planes: List[SplitPlane]) -> List[SplitPlane]:
        global_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        if not global_stack:
            return planes
        intermediate_count = global_stack.getProperty("descrete_mode_intermediate_planes", "value")
        if intermediate_count < 1:
            return planes
        ret = []
        start_normal = numpy.array([0,1,0]).reshape(3)
        start_origin = numpy.array([0,0,0]).reshape(3)
        for plane in planes:
            normal_delta = (plane.normal - start_normal) / (intermediate_count + 1)
            origin_delta = (plane.origin - start_origin) / (intermediate_count + 1)
            for sub_plane_idx in range(0, intermediate_count):
                plane_normal = start_normal + (normal_delta * (sub_plane_idx + 1))
                plane_origin = start_origin + (origin_delta * (sub_plane_idx + 1))
                sub_plane = SplitPlane(plane_normal, plane_origin)
                ret.append(sub_plane)
            ret.append(plane)
            start_normal = plane.normal
            start_origin = plane.origin
        return ret

    def splitNode(self, node: SceneNode, plane: SplitPlane, overlap = 0) -> List[SceneNode]:
        mesh_data = node.getMeshData()
        if mesh_data.hasIndices():
            faces = mesh_data.getIndices()
        else:
            num_verts = mesh_data.getVertexCount()
            faces = numpy.empty((int(num_verts / 3 + 1), 3), numpy.int32)
            for i in range(0, num_verts - 2, 3):
                faces[int(i / 3):] = [i, i + 1, i + 2]
        trmesh = trimesh.Trimesh(vertices=node.getMeshDataTransformed().getVertices(), faces=faces)
        filled = trmesh.fill_holes()
        trmesh.fix_normals()
        trmesh.remove_duplicate_faces()
        plane_normal = plane.normal
        plane_origin = plane.origin
        cut_mesh, start_mesh = SplitByPlane(
            trmesh, plane_normal, plane_origin, True, overlap=overlap)
        start_mesh.fill_holes()
        start_mesh.remove_duplicate_faces()
        start_mesh.fix_normals()
        start_node = SteSlicerSceneNode(node.getParent(), no_setting_override=True)
        if node.hasChildren():
            for child in node.getAllChildren():
                if not child.getDecorator(SplittingPlaneDecorator):
                    start_node.addChild(child)
        start_node.setMeshData(MeshData.MeshData(vertices=start_mesh.vertices.astype('float32'),
                                                 normals=start_mesh.face_normals.astype(
                                                     'float32'),
                                                 indices=start_mesh.faces.astype('int64')))
        start_node.addDecorator(node.getDecorator(SettingOverrideDecorator))
        if cut_mesh:
            cut_mesh.fill_holes()
            cut_mesh.fix_normals()
            cut_mesh.remove_duplicate_faces()
            q = Quaternion.rotationTo(Vector(0,0,1), Vector(-plane_normal[0], plane_normal[2], plane_normal[1]))
            plane_matrix = q.toMatrix()
            cut_node = SteSlicerSceneNode(
                node.getParent(), no_setting_override=True)
            cut_node.setMeshData(MeshData.MeshData(vertices=cut_mesh.vertices.astype('float32'),
                                                   normals=cut_mesh.face_normals.astype(
                                                       'float32'),
                                                   indices=cut_mesh.faces.astype('int64')))
            cut_node.addDecorator(
                node.getDecorator(SettingOverrideDecorator))
            self._direction_matrices[id(cut_node)] = (numpy.array2string(
                plane_matrix.getData()[0:3, 0:3], separator=", ", precision=3, suppress_small=True)).replace('\n',
                                                                                                             ' ').replace(
                '\r', '')

            return [start_node, cut_node]
        return [start_node]

    def cancel(self) -> None:
        super().cancel()
        self._is_cancelled = True

    def isCancelled(self) -> bool:
        return self._is_cancelled

    def setIsCancelled(self, value: bool):
        self._is_cancelled = value

    # Creates a dictionary of tokens to replace in g-code pieces.
    #
    #   This indicates what should be replaced in the start and end g-codes.
    #   \param stack The stack to get the settings from to replace the tokens
    #   with.
    #   \return A dictionary of replacement tokens to the values they should be
    #   replaced with.
    def _buildReplacementTokens(self, stack: ContainerStack) -> Dict[str, Any]:
        result = {}
        for key in stack.getAllKeys():
            value = stack.getProperty(key, "value")
            result[key] = value
            Job.yieldThread()

        # Renamed settings.
        result["print_bed_temperature"] = result["material_bed_temperature"]
        result["print_temperature"] = result["material_print_temperature"]
        result["time"] = time.strftime("%H:%M:%S")  # Some extra settings.
        result["date"] = time.strftime("%d-%m-%Y")
        result["day"] = ["Sun", "Mon", "Tue", "Wed",
                         "Thu", "Fri", "Sat"][int(time.strftime("%w"))]
        printing_mode = result["printing_mode"]
        if printing_mode in ["cylindrical", "cylindrical_full"]:
            result["cylindrical_rotate"] = "G0 A%.2f" % (
                    90 * result["machine_a_axis_multiplier"] / result["machine_a_axis_divider"])
            result["coordinate_system"] = "G56"
        elif printing_mode in ["spherical", "spherical_full"]:
            result["cylindrical_rotate"] = "G0 A0"
            result["coordinate_system"] = "G55"
        elif printing_mode in ["classic"] and result["machine_hybrid"]:
            result["cylindrical_rotate"] = "G4 P100"
            result["coordinate_system"] = "G54"
        elif printing_mode in ["classic"]:
            result["cylindrical_rotate"] = "G0 A0"
            result["coordinate_system"] = "G55"
        elif printing_mode in ["discrete"]:
            result["cylindrical_rotate"] = "G0 A0"
            result["coordinate_system"] = "G55"
            result["prefix_end_gcode"] = "G40"

        initial_extruder_stack = SteSlicerApplication.getInstance(
        ).getExtruderManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty(
            "extruder_nr", "value")
        result["initial_extruder_nr"] = initial_extruder_nr

        return result

    # Replace setting tokens in a piece of g-code.
    #   \param value A piece of g-code to replace tokens in.
    #   \param default_extruder_nr Stack nr to use when no stack nr is specified, defaults to the global stack
    def _expandGcodeTokens(self, value: str, default_extruder_nr: int = -1) -> str:
        if not self._all_extruders_settings:
            global_stack = cast(
                ContainerStack, SteSlicerApplication.getInstance().getGlobalContainerStack())

            # NB: keys must be strings for the string formatter
            self._all_extruders_settings = {
                "-1": self._buildReplacementTokens(global_stack)
            }

            for extruder_stack in ExtruderManager.getInstance().getActiveExtruderStacks():
                extruder_nr = extruder_stack.getProperty(
                    "extruder_nr", "value")
                self._all_extruders_settings[str(
                    extruder_nr)] = self._buildReplacementTokens(extruder_stack)

        try:
            # any setting can be used as a token
            fmt = GcodeStartEndFormatter(
                default_extruder_nr=default_extruder_nr)
            settings = self._all_extruders_settings.copy()
            settings["default_extruder_nr"] = default_extruder_nr
            return str(fmt.format(value, **settings))
        except:
            Logger.logException(
                "w", "Unable to do token replacement on start/end g-code")
            return str(value)

    # Create extruder message from stack
    def _buildExtruderMessage(self, stack: ContainerStack) -> None:
        message = self._slice_message.addRepeatedMessage("extruders")
        message.id = int(stack.getMetaDataEntry("position"))

        settings = self._buildReplacementTokens(stack)

        # Also send the material GUID. This is a setting in fdmprinter, but we have no interface for it.
        settings["material_guid"] = stack.material.getMetaDataEntry("GUID", "")

        # Replace the setting tokens in start and end g-code.
        extruder_nr = stack.getProperty("extruder_nr", "value")
        settings["machine_extruder_start_code"] = self._expandGcodeTokens(
            settings["machine_extruder_start_code"], extruder_nr)
        settings["machine_extruder_end_code"] = self._expandGcodeTokens(
            settings["machine_extruder_end_code"], extruder_nr)
        settings["machine_fiber_cut_code"] = self._expandGcodeTokens(
            settings["machine_fiber_cut_code"], extruder_nr)
        settings["machine_fiber_prime_code"] = self._expandGcodeTokens(
            settings["machine_fiber_prime_code"], extruder_nr)

        for key, value in settings.items():
            # Do not send settings that are not settable_per_extruder.
            if not stack.getProperty(key, "settable_per_extruder"):
                continue
            setting = message.getMessage(
                "settings").addRepeatedMessage("settings")
            setting.name = key
            setting.value = str(value).encode("utf-8")
            Job.yieldThread()

    # Sends all global settings to the engine.
    #
    #   The settings are taken from the global stack. This does not include any
    #   per-extruder settings or per-object settings.
    def _buildGlobalSettingsMessage(self, stack: ContainerStack) -> None:
        settings = self._buildReplacementTokens(stack)

        # Pre-compute material material_bed_temp_prepend and material_print_temp_prepend
        start_gcode = settings["machine_start_gcode"]
        bed_temperature_settings = [
            "material_bed_temperature", "material_bed_temperature_layer_0"]
        # match {setting} as well as {setting, extruder_nr}
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(bed_temperature_settings)
        settings["material_bed_temp_prepend"] = re.search(
            pattern, start_gcode) == None
        print_temperature_settings = ["material_print_temperature", "material_print_temperature_layer_0",
                                      "default_material_print_temperature",
                                      "material_initial_print_temperature", "material_final_print_temperature",
                                      "material_standby_temperature"]
        # match {setting} as well as {setting, extruder_nr}
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(print_temperature_settings)
        settings["material_print_temp_prepend"] = re.search(
            pattern, start_gcode) == None

        # Replace the setting tokens in start and end g-code.
        # Use values from the first used extruder by default so we get the expected temperatures
        initial_extruder_stack = SteSlicerApplication.getInstance(
        ).getExtruderManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty(
            "extruder_nr", "value")

        settings["machine_start_gcode"] = self._expandGcodeTokens(
            settings["machine_start_gcode"], initial_extruder_nr)
        settings["machine_end_gcode"] = self._expandGcodeTokens(
            settings["machine_end_gcode"], initial_extruder_nr)

        printing_mode = settings["printing_mode"]
        if printing_mode in ["discrete"]:
            settings["infill_extruder_nr"] = settings["classic_infill_extruder_nr"]
            settings["speed_infill"] = settings["speed_infill_classic"]
            settings["speed_wall_0"] = settings["speed_wall_0_classic"]
            settings["speed_wall_x"] = settings["speed_wall_x_classic"]
            settings["speed_roofing"] = settings["speed_roofing_classic"]
            settings["speed_topbottom"] = settings["speed_topbottom_classic"]
            settings["speed_support_infill"] = settings["speed_support_infill_classic"]
            settings["speed_travel"] = settings["speed_travel_classic"]
            settings["speed_print_layer_0"] = settings["speed_print_layer_0_classic"]
            settings["speed_travel_layer_0"] = settings["speed_travel_layer_0_classic"]

            settings["cool_fan_enabled"] = settings["cool_fan_enabled_classic"]
            settings["cool_fan_speed_min"] = settings["cool_fan_speed_min_classic"]
            settings["cool_fan_speed_max"] = settings["cool_fan_speed_max_classic"]

        # Add all sub-messages for each individual setting.
        for key, value in settings.items():
            setting_message = self._slice_message.getMessage(
                "global_settings").addRepeatedMessage("settings")
            setting_message.name = key
            setting_message.value = str(value).encode("utf-8")
            Job.yieldThread()

    # Sends for some settings which extruder they should fallback to if not
    #   set.
    #
    #   This is only set for settings that have the limit_to_extruder
    #   property.
    #
    #   \param stack The global stack with all settings, from which to read the
    #   limit_to_extruder property.
    def _buildGlobalInheritsStackMessage(self, stack: ContainerStack) -> None:
        for key in stack.getAllKeys():
            extruder_position = int(
                round(float(stack.getProperty(key, "limit_to_extruder"))))
            if extruder_position >= 0:  # Set to a specific extruder.
                setting_extruder = self._slice_message.addRepeatedMessage(
                    "limit_to_extruder")
                setting_extruder.name = key
                setting_extruder.extruder = extruder_position
            Job.yieldThread()

    # Check if a node has per object settings and ensure that they are set correctly in the message
    #   \param node Node to check.
    #   \param message object_lists message to put the per object settings in
    def _handlePerObjectSettings(self, node: SteSlicerSceneNode, message: Arcus.PythonMessage):
        stack = node.callDecoration("getStack")

        if id(node) in self._direction_matrices.keys():
            setting = message.addRepeatedMessage("settings")
            setting.name = "descrete_mode_mesh_rotation_matrix"
            setting.value = self._direction_matrices.get(id(node)).encode("utf-8")

        # Check if the node has a stack attached to it and the stack has any settings in the top container.
        if not stack:
            return

        # Check all settings for relations, so we can also calculate the correct values for dependent settings.
        top_of_stack = stack.getTop()  # Cache for efficiency.
        changed_setting_keys = top_of_stack.getAllKeys()

        # Add all relations to changed settings as well.
        for key in top_of_stack.getAllKeys():
            instance = top_of_stack.getInstance(key)
            self._addRelations(changed_setting_keys,
                               instance.definition.relations)
            Job.yieldThread()

        # Ensure that the engine is aware what the build extruder is.
        changed_setting_keys.add("extruder_nr")

        # Get values for all changed settings
        for key in changed_setting_keys:
            setting = message.addRepeatedMessage("settings")
            setting.name = key
            extruder = int(
                round(float(stack.getProperty(key, "limit_to_extruder"))))

            # Check if limited to a specific extruder, but not overridden by per-object settings.
            if extruder >= 0 and key not in changed_setting_keys:
                limited_stack = ExtruderManager.getInstance().getActiveExtruderStacks()[
                    extruder]
            else:
                limited_stack = stack

            setting.value = str(limited_stack.getProperty(
                key, "value")).encode("utf-8")

            Job.yieldThread()

    # Recursive function to put all settings that require each other for value changes in a list
    #   \param relations_set Set of keys of settings that are influenced
    #   \param relations list of relation objects that need to be checked.
    def _addRelations(self, relations_set: Set[str], relations: List[SettingRelation]):
        for relation in filter(lambda r: r.role == "value" or r.role == "limit_to_extruder", relations):
            if relation.type == RelationType.RequiresTarget:
                continue

            relations_set.add(relation.target.key)
            self._addRelations(relations_set, relation.target.relations)
