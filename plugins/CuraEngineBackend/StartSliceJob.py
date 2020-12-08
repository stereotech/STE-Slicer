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

from steslicer.Settings.SettingOverrideDecorator import SettingOverrideDecorator
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode
from steslicer.OneAtATimeIterator import OneAtATimeIterator
from steslicer.Settings.ExtruderManager import ExtruderManager
from steslicer.GcodeStartEndFormatter import GcodeStartEndFormatter

NON_PRINTING_MESH_SETTINGS = ["anti_overhang_mesh", "infill_mesh", "cutting_mesh"]


class StartJobResult(IntEnum):
    Finished = 1
    Error = 2
    SettingError = 3
    NothingToSlice = 4
    MaterialIncompatible = 5
    BuildPlateError = 6
    ObjectSettingError = 7 #When an error occurs in per-object settings.
    ObjectsWithDisabledExtruder = 8

##  Job class that builds up the message of scene data to send to CuraEngine.
class StartSliceJob(Job):
    def __init__(self, slice_message: Arcus.PythonMessage) -> None:
        super().__init__()

        self._scene = SteSlicerApplication.getInstance().getController().getScene() #type: Scene
        self._slice_message = slice_message #type: Arcus.PythonMessage
        self._is_cancelled = False #type: bool
        self._build_plate_number = None #type: Optional[int]

        self._all_extruders_settings = None #type: Optional[Dict[str, Any]] # cache for all setting values from all stacks (global & extruder) for the current machine

    def getSliceMessage(self) -> Arcus.PythonMessage:
        return self._slice_message

    def setBuildPlate(self, build_plate_number: int) -> None:
        self._build_plate_number = build_plate_number

    ##  Check if a stack has any errors.
    ##  returns true if it has errors, false otherwise.
    def _checkStackForErrors(self, stack: ContainerStack) -> bool:
        if stack is None:
            return False

        for key in stack.getAllKeys():
            validation_state = stack.getProperty(key, "validationState")
            if validation_state in (ValidatorState.Exception, ValidatorState.MaximumError, ValidatorState.MinimumError):
                Logger.log("w", "Setting %s is not valid, but %s. Aborting slicing.", key, validation_state)
                return True
            Job.yieldThread()
        return False

    ##  Runs the job that initiates the slicing.
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
        for node in DepthFirstIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
            if not isinstance(node, SteSlicerSceneNode) or not node.isSelectable():
                continue

            if self._checkStackForErrors(node.callDecoration("getStack")):
                self.setResult(StartJobResult.ObjectSettingError)
                return

        with self._scene.getSceneLock():
            # Remove old layer data.
            for node in DepthFirstIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                if node.callDecoration("getLayerData") and node.callDecoration("getBuildPlateNumber") == self._build_plate_number:
                    node.getParent().removeChild(node)
                    break

            # Get the objects in their groups to print.
            object_groups = []
            printing_mode = stack.getProperty("printing_mode", "value")
            if printing_mode == "classic":
                if stack.getProperty("print_sequence", "value") == "one_at_a_time":
                    for node in OneAtATimeIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                        temp_list = []

                        # Node can't be printed, so don't bother sending it.
                        if getattr(node, "_outside_buildarea", False):
                            continue

                        # Filter on current build plate
                        build_plate_number = node.callDecoration("getBuildPlateNumber")
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
                        Logger.log("w", "No objects suitable for one at a time found, or no correct order found")
                else:
                    temp_list = []
                    has_printing_mesh = False
                    for node in DepthFirstIterator(self._scene.getRoot()): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                        if node.callDecoration("isSliceable") and node.getMeshData() and node.getMeshData().getVertices() is not None:
                            per_object_stack = node.callDecoration("getStack")
                            is_non_printing_mesh = False
                            if per_object_stack:
                                is_non_printing_mesh = any(per_object_stack.getProperty(key, "value") for key in NON_PRINTING_MESH_SETTINGS)

                            # Find a reason not to add the node
                            if node.callDecoration("getBuildPlateNumber") != self._build_plate_number:
                                continue
                            if getattr(node, "_outside_buildarea", False) and not is_non_printing_mesh:
                                continue

                            temp_list.append(node)
                            if not is_non_printing_mesh:
                                has_printing_mesh = True

                        Job.yieldThread()

                    #If the list doesn't have any model with suitable settings then clean the list
                    # otherwise CuraEngine will crash
                    if not has_printing_mesh:
                        temp_list.clear()

                    if temp_list:
                        object_groups.append(temp_list)
            elif printing_mode in ["cylindrical_full", "spherical_full"]:
                temp_list = []
                has_printing_mesh = False

                for node in DepthFirstIterator(
                        self._scene.getRoot()):  # type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                    if node.callDecoration(
                            "isSliceable") and node.getMeshData() and node.getMeshData().getVertices() is not None:
                        per_object_stack = node.callDecoration("getStack")
                        is_non_printing_mesh = False
                        if per_object_stack:
                            is_non_printing_mesh = any(
                                per_object_stack.getProperty(key, "value") for key in NON_PRINTING_MESH_SETTINGS)

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

            else:
                self.setResult(StartJobResult.ObjectSettingError)
                return

        if temp_list and printing_mode in ["cylindrical_full", "spherical_full"]:
            cut_list = []
            for node in temp_list:
                if printing_mode == "cylindrical_full":
                    radius = SteSlicerApplication.getInstance().getGlobalContainerStack().getProperty(
                        "cylindrical_mode_base_diameter", "value") / 2
                    height = node.getBoundingBox().height * 2
                    cutting_mesh = trimesh.primitives.Cylinder(
                        radius=radius, height=height, sections=64)
                    cutting_mesh.apply_transform(
                        trimesh.transformations.rotation_matrix(numpy.pi / 2, [1, 0, 0]))
                elif printing_mode == "spherical_full":
                    radius = SteSlicerApplication.getInstance().getGlobalContainerStack().getProperty(
                        "spherical_mode_base_radius", "value")
                    cutting_mesh = trimesh.primitives.Sphere(
                        radius=radius, subdivisions=3
                    )
                else:
                    cutting_mesh = None

                mesh_data = node.getMeshData()
                if mesh_data.hasIndices():
                    faces = mesh_data.getIndices()
                else:
                    num_verts = mesh_data.getVertexCount()
                    faces = numpy.empty((int(num_verts / 3 + 1), 3), numpy.int32)
                    for i in range(0, num_verts - 2, 3):
                        faces[int(i / 3):] = [i, i + 1, i + 2]
                verts = mesh_data.getVertices()
                rot_scale = node.getWorldTransformation().getTransposed().getData()[0:3, 0:3]
                translate = node.getWorldTransformation().getData()[:3, 3]
                verts = verts.dot(rot_scale)
                verts += translate
                mesh = trimesh.Trimesh(vertices=verts, faces=faces)
                try:
                    mesh.fill_holes()
                    mesh.fix_normals()
                    cutting_result = mesh.intersection(cutting_mesh, engine="scad")
                    if cutting_result:
                        cutting_result.fill_holes()
                        cutting_result.fix_normals()

                        data = MeshData.MeshData(vertices=cutting_result.vertices.astype('float32'),
                                                 normals=cutting_result.face_normals.astype('float32'),
                                                 indices=cutting_result.faces.astype('int64'))
                        cutting_node = SteSlicerSceneNode(node.getParent(), no_setting_override=True)
                        cutting_node.addDecorator(node.getDecorator(SettingOverrideDecorator))
                except Exception as e:
                    Logger.log("e", "Failed to intersect model! %s", e)
                    cutting_result = cutting_mesh
                    if cutting_result:
                        cutting_result.fill_holes()
                        cutting_result.fix_normals()

                        data = MeshData.MeshData(vertices=cutting_result.vertices.astype('float32'),
                                                 normals=cutting_result.face_normals.astype('float32'),
                                                 indices=cutting_result.faces.astype('int64'))
                        cutting_node = SteSlicerSceneNode(node.getParent(), no_setting_override=True)
                        stack = cutting_node.callDecoration(
                            "getStack")  # Don't try to get the active extruder since it may be None anyway.
                        if not stack:
                            cutting_node.addDecorator(SettingOverrideDecorator())
                            stack = cutting_node.callDecoration("getStack")
                        settings = stack.getTop()
                        if not (settings.getInstance("support_mesh") and settings.getProperty("support_mesh", "value")):
                            definition = stack.getSettingDefinition("support_mesh")
                            new_instance = SettingInstance(definition, settings)
                            new_instance.setProperty("value", True, emit_signals=False)
                            new_instance.resetState()  # Ensure that the state is not seen as a user state.
                            settings.addInstance(new_instance)
                if cutting_node is not None:
                    cutting_node.setName("cut_" + node.getName())
                    cutting_node.setMeshData(data)

                    cut_list.append(cutting_node)

            object_groups.append(cut_list)


        global_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        if not global_stack:
            return
        extruders_enabled = {position: stack.isEnabled for position, stack in global_stack.extruders.items()}
        filtered_object_groups = []
        has_model_with_disabled_extruders = False
        associated_disabled_extruders = set()
        for group in object_groups:
            stack = global_stack
            skip_group = False
            for node in group:
                # Only check if the printing extruder is enabled for printing meshes
                is_non_printing_mesh = node.callDecoration("evaluateIsNonPrintingMesh")
                extruder_position = node.callDecoration("getActiveExtruderPosition")
                if not is_non_printing_mesh and not extruders_enabled[extruder_position]:
                    skip_group = True
                    has_model_with_disabled_extruders = True
                    associated_disabled_extruders.add(extruder_position)
            if not skip_group:
                filtered_object_groups.append(group)

        if has_model_with_disabled_extruders:
            self.setResult(StartJobResult.ObjectsWithDisabledExtruder)
            associated_disabled_extruders = {str(c) for c in sorted([int(p) + 1 for p in associated_disabled_extruders])}
            self.setMessage(", ".join(associated_disabled_extruders))
            return

        # There are cases when there is nothing to slice. This can happen due to one at a time slicing not being
        # able to find a possible sequence or because there are no objects on the build plate (or they are outside
        # the build volume)
        if not filtered_object_groups:
            self.setResult(StartJobResult.NothingToSlice)
            return

        self._buildGlobalSettingsMessage(stack)
        self._buildGlobalInheritsStackMessage(stack)

        # Build messages for extruder stacks
        # Send the extruder settings in the order of extruder positions. Somehow, if you send e.g. extruder 3 first,
        # then CuraEngine can slice with the wrong settings. This I think should be fixed in CuraEngine as well.
        extruder_stack_list = sorted(list(global_stack.extruders.items()), key = lambda item: int(item[0]))
        for _, extruder_stack in extruder_stack_list:
            self._buildExtruderMessage(extruder_stack)

        for group in filtered_object_groups:
            group_message = self._slice_message.addRepeatedMessage("object_lists")
            if group[0].getParent() is not None and group[0].getParent().callDecoration("isGroup"):
                self._handlePerObjectSettings(group[0].getParent(), group_message)
            for object in group:
                mesh_data = object.getMeshData()
                rot_scale = object.getWorldTransformation().getTransposed().getData()[0:3, 0:3]
                translate = object.getWorldTransformation().getData()[:3, 3]

                # This effectively performs a limited form of MeshData.getTransformed that ignores normals.
                verts = mesh_data.getVertices()
                verts = verts.dot(rot_scale)
                if printing_mode == "classic":
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

    def cancel(self) -> None:
        super().cancel()
        self._is_cancelled = True

    def isCancelled(self) -> bool:
        return self._is_cancelled

    def setIsCancelled(self, value: bool):
        self._is_cancelled = value

    ##  Creates a dictionary of tokens to replace in g-code pieces.
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

        result["print_bed_temperature"] = result["material_bed_temperature"] # Renamed settings.
        result["print_temperature"] = result["material_print_temperature"]
        result["time"] = time.strftime("%H:%M:%S") #Some extra settings.
        result["date"] = time.strftime("%d-%m-%Y")
        result["day"] = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][int(time.strftime("%w"))]
        printing_mode = result["printing_mode"]
        if printing_mode in ["cylindrical", "cylindrical_full"]:
            result["cylindrical_rotate"] = "G0 A%.2f" % (
                        90 * result["machine_a_axis_multiplier"] / result["machine_a_axis_divider"])
            result["coordinate_system"] = "G56"
        elif printing_mode in ["spherical", "spherical_full"]:
            result["cylindrical_rotate"] = "G0 A0"
            result["coordinate_system"] = "G55"
        elif printing_mode in ["classic"]:
            result["cylindrical_rotate"] = "G0 A0"
            result["coordinate_system"] = "G55"

        initial_extruder_stack = SteSlicerApplication.getInstance().getExtruderManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty("extruder_nr", "value")
        result["initial_extruder_nr"] = initial_extruder_nr

        return result

    ##  Replace setting tokens in a piece of g-code.
    #   \param value A piece of g-code to replace tokens in.
    #   \param default_extruder_nr Stack nr to use when no stack nr is specified, defaults to the global stack
    def _expandGcodeTokens(self, value: str, default_extruder_nr: int = -1) -> str:
        if not self._all_extruders_settings:
            global_stack = cast(ContainerStack, SteSlicerApplication.getInstance().getGlobalContainerStack())

            # NB: keys must be strings for the string formatter
            self._all_extruders_settings = {
                "-1": self._buildReplacementTokens(global_stack)
            }

            for extruder_stack in ExtruderManager.getInstance().getActiveExtruderStacks():
                extruder_nr = extruder_stack.getProperty("extruder_nr", "value")
                self._all_extruders_settings[str(extruder_nr)] = self._buildReplacementTokens(extruder_stack)

        try:
            # any setting can be used as a token
            fmt = GcodeStartEndFormatter(default_extruder_nr = default_extruder_nr)
            settings = self._all_extruders_settings.copy()
            settings["default_extruder_nr"] = default_extruder_nr
            return str(fmt.format(value, **settings))
        except:
            Logger.logException("w", "Unable to do token replacement on start/end g-code")
            return str(value)

    ##  Create extruder message from stack
    def _buildExtruderMessage(self, stack: ContainerStack) -> None:
        message = self._slice_message.addRepeatedMessage("extruders")
        message.id = int(stack.getMetaDataEntry("position"))

        settings = self._buildReplacementTokens(stack)

        # Also send the material GUID. This is a setting in fdmprinter, but we have no interface for it.
        settings["material_guid"] = stack.material.getMetaDataEntry("GUID", "")

        # Replace the setting tokens in start and end g-code.
        extruder_nr = stack.getProperty("extruder_nr", "value")
        settings["machine_extruder_start_code"] = self._expandGcodeTokens(settings["machine_extruder_start_code"], extruder_nr)
        settings["machine_extruder_end_code"] = self._expandGcodeTokens(settings["machine_extruder_end_code"], extruder_nr)
        settings["machine_fiber_cut_code"] = self._expandGcodeTokens(settings["machine_fiber_cut_code"], extruder_nr)
        settings["machine_fiber_prime_code"] = self._expandGcodeTokens(settings["machine_fiber_prime_code"], extruder_nr)

        for key, value in settings.items():
            # Do not send settings that are not settable_per_extruder.
            if not stack.getProperty(key, "settable_per_extruder"):
                continue
            setting = message.getMessage("settings").addRepeatedMessage("settings")
            setting.name = key
            setting.value = str(value).encode("utf-8")
            Job.yieldThread()

    ##  Sends all global settings to the engine.
    #
    #   The settings are taken from the global stack. This does not include any
    #   per-extruder settings or per-object settings.
    def _buildGlobalSettingsMessage(self, stack: ContainerStack) -> None:
        settings = self._buildReplacementTokens(stack)

        # Pre-compute material material_bed_temp_prepend and material_print_temp_prepend
        start_gcode = settings["machine_start_gcode"]
        bed_temperature_settings = ["material_bed_temperature", "material_bed_temperature_layer_0"]
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(bed_temperature_settings) # match {setting} as well as {setting, extruder_nr}
        settings["material_bed_temp_prepend"] = re.search(pattern, start_gcode) == None
        print_temperature_settings = ["material_print_temperature", "material_print_temperature_layer_0", "default_material_print_temperature", "material_initial_print_temperature", "material_final_print_temperature", "material_standby_temperature"]
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(print_temperature_settings) # match {setting} as well as {setting, extruder_nr}
        settings["material_print_temp_prepend"] = re.search(pattern, start_gcode) == None

        # Replace the setting tokens in start and end g-code.
        # Use values from the first used extruder by default so we get the expected temperatures
        initial_extruder_stack = SteSlicerApplication.getInstance().getExtruderManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty("extruder_nr", "value")

        settings["machine_start_gcode"] = self._expandGcodeTokens(settings["machine_start_gcode"], initial_extruder_nr)
        settings["machine_end_gcode"] = self._expandGcodeTokens(settings["machine_end_gcode"], initial_extruder_nr)

        printing_mode = settings["printing_mode"]
        if printing_mode in ["classic", "cylindrical_full"]:
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
            setting_message = self._slice_message.getMessage("global_settings").addRepeatedMessage("settings")
            setting_message.name = key
            setting_message.value = str(value).encode("utf-8")
            Job.yieldThread()

    ##  Sends for some settings which extruder they should fallback to if not
    #   set.
    #
    #   This is only set for settings that have the limit_to_extruder
    #   property.
    #
    #   \param stack The global stack with all settings, from which to read the
    #   limit_to_extruder property.
    def _buildGlobalInheritsStackMessage(self, stack: ContainerStack) -> None:
        for key in stack.getAllKeys():
            extruder_position = int(round(float(stack.getProperty(key, "limit_to_extruder"))))
            if extruder_position >= 0:  # Set to a specific extruder.
                setting_extruder = self._slice_message.addRepeatedMessage("limit_to_extruder")
                setting_extruder.name = key
                setting_extruder.extruder = extruder_position
            Job.yieldThread()

    ##  Check if a node has per object settings and ensure that they are set correctly in the message
    #   \param node Node to check.
    #   \param message object_lists message to put the per object settings in
    def _handlePerObjectSettings(self, node: SteSlicerSceneNode, message: Arcus.PythonMessage):
        stack = node.callDecoration("getStack")

        # Check if the node has a stack attached to it and the stack has any settings in the top container.
        if not stack:
            return

        # Check all settings for relations, so we can also calculate the correct values for dependent settings.
        top_of_stack = stack.getTop()  # Cache for efficiency.
        changed_setting_keys = top_of_stack.getAllKeys()

        # Add all relations to changed settings as well.
        for key in top_of_stack.getAllKeys():
            instance = top_of_stack.getInstance(key)
            self._addRelations(changed_setting_keys, instance.definition.relations)
            Job.yieldThread()

        # Ensure that the engine is aware what the build extruder is.
        changed_setting_keys.add("extruder_nr")

        # Get values for all changed settings
        for key in changed_setting_keys:
            setting = message.addRepeatedMessage("settings")
            setting.name = key
            extruder = int(round(float(stack.getProperty(key, "limit_to_extruder"))))

            # Check if limited to a specific extruder, but not overridden by per-object settings.
            if extruder >= 0 and key not in changed_setting_keys:
                limited_stack = ExtruderManager.getInstance().getActiveExtruderStacks()[extruder]
            else:
                limited_stack = stack

            setting.value = str(limited_stack.getProperty(key, "value")).encode("utf-8")

            Job.yieldThread()

    ##  Recursive function to put all settings that require each other for value changes in a list
    #   \param relations_set Set of keys of settings that are influenced
    #   \param relations list of relation objects that need to be checked.
    def _addRelations(self, relations_set: Set[str], relations: List[SettingRelation]):
        for relation in filter(lambda r: r.role == "value" or r.role == "limit_to_extruder", relations):
            if relation.type == RelationType.RequiresTarget:
                continue

            relations_set.add(relation.target.key)
            self._addRelations(relations_set, relation.target.relations)

