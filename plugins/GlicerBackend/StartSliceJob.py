

import numpy
from string import Formatter
from enum import IntEnum
import time
from typing import Any, cast, Dict, List, Optional, Set
import re
import Arcus #For typing.

from UM.Job import Job
from UM.Logger import Logger
from UM.Settings.ContainerStack import ContainerStack #For typing.
from UM.Settings.SettingRelation import SettingRelation #For typing.

from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Scene.Scene import Scene #For typing.
from UM.Settings.Validator import ValidatorState
from UM.Settings.SettingRelation import RelationType

from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode
from steslicer.OneAtATimeIterator import OneAtATimeIterator
from steslicer.Settings.ExtruderManager import ExtruderManager
from steslicer.GcodeStartEndFormatter import GcodeStartEndFormatter

import xml.etree.ElementTree as eltree
import tempfile
import trimesh
import trimesh.primitives
import trimesh.repair

NON_PRINTING_MESH_SETTINGS = ["anti_overhang_mesh", "infill_mesh", "cutting_mesh"]

params_dict = {
    "Camera": {'xsize': {
        "stack_key": "machine_width",
        "default_value": 200,
    }, 'ysize': {
        "stack_key": "machine_depth",
        "default_value": 200,
    }, 'zsize': {
        "stack_key": "machine_height",
        "default_value": 200
    }, 'rsize': {
        "stack_key": "machine_width",
        "default_value": 100
    }, 'round': {
        "stack_key": "",
        "default_value": 1
    }, 'zones': {
        "stack_key": "",
        "default_value": ""
    }, 'segmentcount': {
        "stack_key": "",
        "default_value": 32
    }, 'minimize_height': {
        "stack_key": "",
        "default_value": 0
    }, 'minimize_square': {
        "stack_key": "",
        "default_value": 1
    }, 'delta': {
        "stack_key": "",
        "default_value": 0.5
    }, 'center': {
        "stack_key": "machine_center_is_zero",
        "default_value": 1
    }, '_shadows': {
        "stack_key": "",
        "default_value": 1
    }},
    "Slice": {
        "z_step": {
            "stack_key": "layer_height",
            "default_value": 0.2
        },
        "r_step": {
            "stack_key": "layer_height",
            "default_value": 0.2
        },
        "round": {
            "stack_key": "",
            "default_value": 1
        },
        "simplify_contours": {
            "stack_key": "",
            "default_value": 1
        },
    },
    "GCode": {
        "cli_quality": {
            "stack_key": "",
            "default_value": 3
        },
        "head_size": {
            "stack_key": "",
            "default_value": 0.01
        },
        "main_offset": {
            "stack_key": "line_width",
            "default_value": 0.4
        },
        "first_offset": {
            "stack_key": "line_width",
            "default_value": 0.2
        },
        "last_offset": {
            "stack_key": "line_width",
            "default_value": 0.2
        },
        "perimeter_count": {
            "stack_key": "wall_line_count",
            "default_value": 2
        },
        "infill_width": {
            "stack_key": "infill_line_distance",
            "default_value": 2
        },
        "infill_fast": {
            "stack_key": "",
            "default_value": 2
        },
        "infill_angle": {
            "stack_key": "",
            "default_value": 45
        },
        "infill_shift": {
            "stack_key": "",
            "default_value": 0
        },
        "fdm_speed": {
            "stack_key": "",
            "default_value": 0
        },
        "units": {
            "stack_key": "",
            "default_value": 1
        },
        "keep_bounds": {
            "stack_key": "",
            "default_value": 1
        },
        "type": {
            "stack_key": "",
            "default_value": "C"
        },
        "skin_width": {
            "stack_key": "bottom_layers",
            "default_value": 4
        },
        "infill_round_width": {
            "stack_key": "skin_line_width",
            "default_value": 0.4
        },
    },
    "GCodeSupport": {
        "first_offset": {
            "stack_key": "",
            "default_value": 0
        },
        "main_offset": {
            "stack_key": "",
            "default_value": 0.1
        },
        "last_offset": {
            "stack_key": "",
            "default_value": 0
        },
        "perimeter_count": {
            "stack_key": "support_wall_count",
            "default_value": 0
        },
        "infill_width": {
            "stack_key": "support_line_distance",
            "default_value": 2.66
        },
        "infill_angle": {
            "stack_key": "",
            "default_value": 0
        },
        "infill_fast": {
            "stack_key": "",
            "default_value": 2
        },
    },
    "Support": {
        "support_base_r": {
            "stack_key": "cylindrical_mode_base_diameter",
            "default_value": 3
        },
        "supportangle": {
            "stack_key": "support_angle",
            "default_value": 50
        },
        "customangle": {
            "stack_key": "",
            "default_value": 6
        },
    },
    "SupportPattern": {
        "cx": {
            "stack_key": "",
            "default_value": 10
        },
        "cy": {
            "stack_key": "",
            "default_value": 10
        },
        "k": {
            "stack_key": "",
            "default_value": 1
        },
        "spline": {
            "stack_key": "",
            "default_value": 0
        },
        "perimeter": {
            "stack_key": "",
            "default_value": 0
        },
        "perimeter_width": {
            "stack_key": "",
            "default_value": 0.5
        },
        "perimeter_step": {
            "stack_key": "",
            "default_value": 0.5
        },
        "perimeter_holes": {
            "stack_key": "",
            "default_value": 1
        },
        "hedge": {
            "stack_key": "",
            "default_value": 1
        },
        "hedgeinbody": {
            "stack_key": "",
            "default_value": 0
        },
        "bridgesheight": {
            "stack_key": "",
            "default_value": "_0.5"
        },
        "bridgesspaces": {
            "stack_key": "",
            "default_value": "_1"
        },
        "bridgesoffset": {
            "stack_key": "",
            "default_value": "_0"
        },
        "patternholes": {
            "stack_key": "",
            "default_value": ""
        },
        "holesheight": {
            "stack_key": "",
            "default_value": "_0.5"
        },
    }
}

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
    def __init__(self, slice_message):
        super().__init__()

        self._scene = SteSlicerApplication.getInstance().getController().getScene() #type: Scene
        self._slice_message = slice_message
        self._is_cancelled = False  # type: bool
        self._build_plate_number = None  # type: Optional[int]

        self._all_extruders_settings = None  # type: Optional[Dict[str, Any]] # cache for all setting values from all stacks (global & extruder) for the current machine

    def setBuildPlate(self, build_plate_number: int) -> None:
        self._build_plate_number = build_plate_number

    def getSliceMessage(self) -> List[str]:
        return self._slice_message

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

    def cancel(self) -> None:
        super().cancel()
        self._is_cancelled = True

    def isCancelled(self) -> bool:
        return self._is_cancelled

    def setIsCancelled(self, value: bool):
        self._is_cancelled = value

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

            object_groups = []
            printing_mode = stack.getProperty("printing_mode", "value")
            if printing_mode in ["cylindrical", "cylindrical_full"]:
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
            extruders_enabled = {position: stack.isEnabled for position, stack in global_stack.extruders.items()}
            filtered_object_groups = []
            has_model_with_disabled_extruders = False
            associated_disabled_extruders = set()
            for group in object_groups:
                #stack = global_stack
                stack = SteSlicerApplication.getInstance().getExtruderManager().getActiveExtruderStack()
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

            if not filtered_object_groups:
                self.setResult(StartJobResult.NothingToSlice)
                return

            self._buildGlobalSettingsMessage(stack)

            indicies_collection = []
            vertices_collection = []
            for group in filtered_object_groups:
                for object in group:
                    mesh_data = object.getMeshData()
                    rot_scale = object.getWorldTransformation().getTransposed().getData()[0:3, 0:3]
                    translate = object.getWorldTransformation().getData()[:3, 3]

                    # This effectively performs a limited form of MeshData.getTransformed that ignores normals.
                    verts = mesh_data.getVertices()
                    verts = verts.dot(rot_scale)
                    verts += translate

                    # Convert from Y up axes to Z up axes. Equals a 90 degree rotation.
                    verts[:, [1, 2]] = verts[:, [2, 1]]
                    verts[:, 1] *= -1

                    if mesh_data.hasIndices():
                        faces = mesh_data.getIndices()
                    else:
                        num_verts = mesh_data.getVertexCount()
                        faces = numpy.empty((int(num_verts / 3 + 1), 3), numpy.int32)
                        for i in range(0, num_verts - 2, 3):
                            faces[int(i / 3):] = [i, i + 1, i + 2]
                    if faces is None:
                        continue
                    if faces is not None:
                        flat_verts = numpy.take(verts, faces.flatten(), axis=0)
                    else:
                        flat_verts = numpy.array(verts)
                    indicies_collection.append(faces)
                    vertices_collection.append(flat_verts)

                    Job.yieldThread()
            self._buildObjectFiles(indicies_collection, vertices_collection)

        self.setResult(StartJobResult.Finished)

    def _buildObjectFiles(self, indicies_collection, vertices_collection):
        mesh_collection = []
        for index, vertices in enumerate(vertices_collection):
            mesh = trimesh.Trimesh(vertices=vertices, faces=indicies_collection[index])
            mesh_collection.append(mesh)
            Job.yieldThread()
        output_mesh = trimesh.util.concatenate(mesh_collection) #type: trimesh.Trimesh
        trimesh.repair.fix_winding(output_mesh)
        Job.yieldThread()
        trimesh.repair.fix_inversion(output_mesh, multibody=True)
        output_mesh.fill_holes()
        output_mesh.fix_normals()
        # create_cutting_cylinder
        global_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        radius = global_stack.getProperty("cylindrical_mode_base_diameter", "value") / 2
        height = global_stack.getProperty("machine_height", "value")
        cutting_cylinder = trimesh.primitives.Cylinder(
            radius=radius, height=height, sections=64)

        # cut mesh by cylinder
        try:
            result = output_mesh.difference(cutting_cylinder, engine="scad")
        except Exception as e:
            Logger.log("e", "Exception while differece model! %s", e)
            result = output_mesh
        temp_mesh = tempfile.NamedTemporaryFile('w', delete=False)
        result.export(temp_mesh.name, 'stl')


        self._slice_message.append('-m')
        self._slice_message.append(temp_mesh.name)


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
            fmt = GcodeStartEndFormatter(default_extruder_nr=default_extruder_nr)
            settings = self._all_extruders_settings.copy()
            settings["default_extruder_nr"] = default_extruder_nr
            return str(fmt.format(value, **settings))
        except:
            Logger.logException("w", "Unable to do token replacement on start/end g-code")
            return str(value)

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

        result["print_bed_temperature"] = result["material_bed_temperature"]  # Renamed settings.
        result["print_temperature"] = result["material_print_temperature"]
        result["time"] = time.strftime("%H:%M:%S")  # Some extra settings.
        result["date"] = time.strftime("%d-%m-%Y")
        result["day"] = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][int(time.strftime("%w"))]

        initial_extruder_stack = SteSlicerApplication.getInstance().getExtruderManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty("extruder_nr", "value")
        result["initial_extruder_nr"] = initial_extruder_nr

        return result

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

        temp_config = tempfile.NamedTemporaryFile('w', delete=False, encoding='Windows-1251')
        self._generateGlicerConfig(temp_config.name, settings)

        self._slice_message.append('-c')
        self._slice_message.append(temp_config.name)


    def _generateGlicerConfig(self, filename: str, settings: Dict) -> None:
        root = eltree.Element("root")
        normalize = "normalize_when_load"
        sub = eltree.SubElement(root, "param", attrib={'NAME': normalize, 'PARAM': ''})
        sub.text = "0"
        for region, params in params_dict.items():
            for name, value in params.items():
                sub = eltree.SubElement(root, "param", attrib={'NAME': name, 'REGION': region, 'PARAM': ''})
                setting_value = settings.get(value.get("stack_key", ""), None)
                if setting_value is not None:
                    if isinstance(setting_value, bool):
                        if setting_value:
                            setting_value = "1"
                        else:
                            setting_value = "0"
                    if name in ["rsize", "first_offset", "last_offset", "support_base_r"]:
                        setting_value /= 2
                    if name == "skin_width":
                        setting_value = setting_value if setting_value <= 4 else 4
                    if name == "supportangle":
                        supports_enabled = settings.get("support_enable_cylindrical", False)
                        setting_value = 90 - setting_value if supports_enabled else "0"

                else:
                    setting_value = value.get("default_value", "")
                sub.text = setting_value.__str__()
                Job.yieldThread()
        settings_string = eltree.tostring(root, encoding='Windows-1251').decode("Windows-1251")
        with open(filename, mode='w') as f:
            f.write(settings_string)
