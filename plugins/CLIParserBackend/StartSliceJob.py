import os
import subprocess

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
            "stack_key": "cylindrical_layer_height",
            "default_value": 0.2
        },
        "r_step": {
            "stack_key": "cylindrical_layer_height",
            "default_value": 0.2
        },
        "r_step0": {
            "stack_key": "cylindrical_layer_height_0",
            "default_value": 0.3
        },
        "r_start": {
            "stack_key": "cylindrical_mode_base_diameter",
            "default_value": 3
        },
        "round": {
            "stack_key": "",
            "default_value": 1
        },
        "simplify_contours": {
            "stack_key": "",
            "default_value": 1
        },
        "support_model_delta_round": {
            "stack_key": "",
            "default_value": 1
        }
    },
    "GCode": {
        "cli_quality": {
            "stack_key": "",
            "default_value": 4
        },
        "outorder": {
            "stack_key": "",
            "default_value": "PORCIUD"
            
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
        "upskin_width": {
            "stack_key": "top_layers",
            "default_value": 4
        },
        "downskin_width": {
            "stack_key": "bottom_layers",
            "default_value": 4
        },
        "infill_round_double": {
          "stack_key": "infill_pattern",
          "default_value": 0
        },
        "infill_round_connect": {
          "stack_key": "zig_zaggify_infill",
          "default_value": 0
        },
        "infill_round_width": {
            "stack_key": "skin_line_width",
            "default_value": 0.4
        },
        "split_layer_contours": {
            "stack_key": "",
            "default_value": 1
        },
        "infill_main_offset": {
            "stack_key": "fill_perimeter_gaps",
            "default_value": 1
        },
        "composite_layer_start": {
            "stack_key": "reinforcement_start_layer",
            "default": 10
        },
        "composite_layer_count": {
            "stack_key": "reinforcement_layer_count",
            "default": 2
        },
        "composite_width": {
            "stack_key": "fiber_infill_line_width",
            "default": 0.9
        },
        "composite_round_segm": {
            "stack_key": "",
            "default": 16
        },
        "composite_round_radius": {
            "stack_key": "",
            "default": 1
        },
        "composite_round": {
            "stack_key": "",
            "default": 4
        },
        "composite_min_length": {
            "stack_key": "",#"reinforcement_min_fiber_line_length",
            "default": 999999
        },
        "composite_bottom_skin": {
            "stack_key": "reinforcement_bottom_skin_layers",
            "default": 4,
        },
        "composite_top_skin": {
            "stack_key": "reinforcement_top_skin_layers",
            "default": 1
        }
    },
    "GCodeSupport": {
        "first_offset": {
            "stack_key": "support_first_offset",
            "default_value": 0.1
        },
        "main_offset": {
            "stack_key": "support_offset",
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
    def __init__(self, slice_message, arcus_message: Arcus.PythonMessage):
        super().__init__()

        self._scene = SteSlicerApplication.getInstance().getController().getScene() #type: Scene
        self._slice_message = slice_message
        self._arcus_message = arcus_message
        self._is_cancelled = False  # type: bool
        self._build_plate_number = None  # type: Optional[int]

        self._all_extruders_settings = None  # type: Optional[Dict[str, Any]] # cache for all setting values from all stacks (global & extruder) for the current machine

    def setBuildPlate(self, build_plate_number: int) -> None:
        self._build_plate_number = build_plate_number

    def getSliceMessage(self) -> List[str]:
        return self._slice_message

    def getArcusMessage(self) -> Arcus.PythonMessage:
        return self._arcus_message
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
            if printing_mode in ["cylindrical", "cylindrical_full", "spherical", "spherical_full"]:
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
                stack = global_stack
                #stack = SteSlicerApplication.getInstance().getExtruderManager().getActiveExtruderStack()
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

            self._buildGlicerConfigMessage(SteSlicerApplication.getInstance().getExtruderManager().getActiveExtruderStack())

            self._buildGlobalSettingsMessage(stack)
            self._buildGlobalInheritsStackMessage(stack)

            extruder_stack_list = sorted(list(global_stack.extruders.items()), key=lambda item: int(item[0]))
            for _, extruder_stack in extruder_stack_list:
                self._buildExtruderMessage(extruder_stack)

            indicies_collection = []
            vertices_collection = []
            for group in filtered_object_groups:
                cli_list_message = self._arcus_message.addRepeatedMessage("cli_lists")
                if group[0].getParent() is not None and group[0].getParent().callDecoration("isGroup"):
                    self._handlePerObjectSettings(group[0].getParent(), cli_list_message)
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

                    cli = cli_list_message.addRepeatedMessage("cli")
                    cli.id = id(object)
                    cli.name = object.getName()
                    self._handlePerObjectSettings(object, cli)

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
        printing_mode = global_stack.getProperty("printing_mode", "value")
        try:
            if printing_mode in ["cylindrical", "cylindrical_full"]:
                radius = global_stack.getProperty("cylindrical_mode_base_diameter", "value") / 2 # + global_stack.getProperty("cylindrical_layer_height", "value")
                height = global_stack.getProperty("machine_height", "value") * 2
                if radius <= 15:
                    section = 64
                elif 15 < radius <= 30:
                    section = 256
                else:
                    section = 1024
                cutting_mesh = trimesh.primitives.Cylinder(
                    radius=radius, height=height, sections=section)
            elif printing_mode in ["spherical", "spherical_full"]:
                radius = global_stack.getProperty("spherical_mode_base_radius", "value")
                overlap = global_stack.getProperty("cylindrical_mode_overlap", "value") / 2
                if radius > 0:
                    radius += global_stack.getProperty(
                        "cylindrical_layer_height", "value")
                else:
                    raise ValueError
                cutting_mesh = trimesh.primitives.Sphere(
                    radius=radius - overlap, subdivisions = 3
                )
            # cut mesh by cylinder
            result = output_mesh.difference(cutting_mesh, engine="scad")
        except Exception as e:
            Logger.log("e", "Exception while differece model! %s", e)
            result = output_mesh
        temp_mesh = tempfile.NamedTemporaryFile('w', delete=False)
        raft_thickness = (
                global_stack.getProperty("raft_base_thickness", "value") +
                global_stack.getProperty("raft_interface_thickness", "value") +
                global_stack.getProperty("raft_surface_layers", "value") *
                global_stack.getProperty("raft_surface_thickness", "value") +
                global_stack.getProperty("raft_airgap", "value") -
                global_stack.getProperty("layer_0_z_overlap", "value"))
        if global_stack.getProperty("adhesion_type", "value") == "raft":
            result.apply_translation([0,0,raft_thickness])
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
        printing_mode = result["printing_mode"]
        if printing_mode in ["cylindrical_full", "cylindrical"]:
            result["cylindrical_rotate"] = "G0 A%.2f" % (90 * result["machine_a_axis_multiplier"] / result["machine_a_axis_divider"])
            result["coordinate_system"] = "G56"
        elif printing_mode in ["spherical_full", "spherical"]:
            result["cylindrical_rotate"] = "G0 A0"
            result["coordinate_system"] = "G55"

        initial_extruder_stack = SteSlicerApplication.getInstance().getExtruderManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty("extruder_nr", "value")
        result["initial_extruder_nr"] = initial_extruder_nr

        return result

    def _buildGlicerConfigMessage(self, stack: ContainerStack) -> None:
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
                        if name == "support_base_r":
                            setting_value += settings.get("cylindrical_layer_height", 0.2)
                        if name == "first_offset" and region =="GCodeSupport":
                            setting_value = settings.get("support_first_offset")
                    if name in ["upskin_width", "downskin_width"]:
                       setting_value = setting_value if setting_value < 100 else 100
                    if name == "supportangle":
                        supports_enabled = settings.get("support_enable_cylindrical", False)
                        setting_value = 90 - setting_value if supports_enabled else "0"
                    if name == "perimeter_count":
                        printing_mode = settings.get("printing_mode", "classic")
                        infill_pattern = settings.get("infill_pattern", "lines")
                        if printing_mode in ["spherical", "spherical_full"]:
                            setting_value = -1
                    if name == "infill_round_double":
                        if setting_value == "grid":
                            setting_value = "1"
                        elif setting_value == "concentric":
                            setting_value = "2"
                        else:
                            setting_value = "0"
                    if name == "fill_perimeter_gaps":
                        if setting_value == "nowhere":
                            setting_value = "0"
                        elif setting_value == "everywhere":
                            setting_value = "1"
                        else:
                            setting_value = "1"
                    if name == "r_start":
                        setting_value = (settings.get("cylindrical_mode_base_diameter")-settings.get("cylindrical_mode_overlap"))/2
                    if name == "r_step0":
                        setting_value = settings.get("cylindrical_layer_height_0")
                else:
                    setting_value = value.get("default_value", "")
                    if name == "round":
                        printing_mode = settings.get("printing_mode", "classic")
                        if printing_mode in ["cylindrical", "cylindrical_full"]:
                            setting_value = 1
                        elif printing_mode in ["spherical", "spherical_full"]:
                            setting_value = 2
                    if name == "support_base_r":
                        printing_mode = settings.get("printing_mode", "classic")
                        if printing_mode in ["spherical", "spherical_full"]:
                            setting_value = 0
                    if name == "support_model_delta_round":
                        setting_value = settings.get("support_z_distance", 0.1) / settings.get("cylindrical_layer_height", 0.1)


                sub.text = setting_value.__str__()
                Job.yieldThread()
        settings_string = eltree.tostring(root, encoding='Windows-1251').decode("Windows-1251")
        with open(filename, mode='w') as f:
            f.write(settings_string)

    def _buildGlobalSettingsMessage(self, stack: ContainerStack) -> None:
        settings = self._buildReplacementTokens(stack)

        # Pre-compute material material_bed_temp_prepend and material_print_temp_prepend
        start_gcode = settings["machine_start_gcode"]
        bed_temperature_settings = ["material_bed_temperature", "material_bed_temperature_layer_0"]
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(
            bed_temperature_settings)  # match {setting} as well as {setting, extruder_nr}
        settings["material_bed_temp_prepend"] = re.search(pattern, start_gcode) == None
        print_temperature_settings = ["material_print_temperature", "material_print_temperature_layer_0",
                                      "default_material_print_temperature", "material_initial_print_temperature",
                                      "material_final_print_temperature", "material_standby_temperature"]
        pattern = r"\{(%s)(,\s?\w+)?\}" % "|".join(
            print_temperature_settings)  # match {setting} as well as {setting, extruder_nr}
        settings["material_print_temp_prepend"] = re.search(pattern, start_gcode) == None

        # Replace the setting tokens in start and end g-code.
        # Use values from the first used extruder by default so we get the expected temperatures
        initial_extruder_stack = SteSlicerApplication.getInstance().getExtruderManager().getUsedExtruderStacks()[0]
        initial_extruder_nr = initial_extruder_stack.getProperty("extruder_nr", "value")

        settings["machine_start_gcode"] = self._expandGcodeTokens(settings["machine_start_gcode"], initial_extruder_nr)
        settings["machine_middle_gcode"] = self._expandGcodeTokens(settings["machine_middle_gcode"], initial_extruder_nr)
        settings["machine_end_gcode"] = self._expandGcodeTokens(settings["machine_end_gcode"], initial_extruder_nr)

        printing_mode = settings["printing_mode"]
        if printing_mode in ["cylindrical", "cylindrical_full"]:
            settings["infill_extruder_nr"] = settings["cylindrical_infill_extruder_nr"]
            settings["speed_infill"] = settings["speed_infill_cylindrical"]
            settings["speed_wall_0"] = settings["speed_wall_0_cylindrical"]
            settings["speed_wall_x"] = settings["speed_wall_x_cylindrical"]
            settings["speed_roofing"] = settings["speed_roofing_cylindrical"]
            settings["speed_topbottom"] = settings["speed_topbottom_cylindrical"]
            settings["speed_support_infill"] = settings["speed_support_infill_cylindrical"]
            settings["speed_travel"] = settings["speed_travel_cylindrical"]
            settings["speed_print_layer_0"] = settings["speed_print_layer_0_cylindrical"]
            settings["speed_travel_layer_0"] = settings["speed_travel_layer_0_cylindrical"]

            settings["cool_fan_enabled"] = settings["cool_fan_enabled_cylindrical"]
            settings["cool_fan_speed_min"] = settings["cool_fan_speed_min_cylindrical"]
            settings["cool_fan_speed_max"] = settings["cool_fan_speed_max_cylindrical"]

            settings["fiber_infill_extruder_nr"] = settings["cylindrical_fiber_infill_extruder_nr"]

            settings["layer_height_0"] = settings["cylindrical_layer_height_0"]

            settings["magic_spiralize"] = False



        # Add all sub-messages for each individual setting.
        for key, value in settings.items():
            setting_message = self._arcus_message.getMessage("global_settings").addRepeatedMessage("settings")
            setting_message.name = key
            setting_message.value = str(value).encode("utf-8")
            Job.yieldThread()

    def _buildGlobalInheritsStackMessage(self, stack: ContainerStack) -> None:
        for key in stack.getAllKeys():
            extruder_position = int(round(float(stack.getProperty(key, "limit_to_extruder"))))
            if extruder_position >= 0:  # Set to a specific extruder.
                setting_extruder = self._arcus_message.addRepeatedMessage("limit_to_extruder")
                setting_extruder.name = key
                setting_extruder.extruder = extruder_position
            Job.yieldThread()

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

    def _addRelations(self, relations_set: Set[str], relations: List[SettingRelation]):
        for relation in filter(lambda r: r.role == "value" or r.role == "limit_to_extruder", relations):
            if relation.type == RelationType.RequiresTarget:
                continue

            relations_set.add(relation.target.key)
            self._addRelations(relations_set, relation.target.relations)

    def _buildExtruderMessage(self, stack: ContainerStack) -> None:
        message = self._arcus_message.addRepeatedMessage("extruders")
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

    def getQuickCsgCommand(self) -> List[str]:
        executable_name = "occ-csg.exe"
        default_engine_location = executable_name
        if os.path.exists(os.path.join(SteSlicerApplication.getInstallPrefix(), "bin", executable_name)):
            default_engine_location = os.path.join(SteSlicerApplication.getInstallPrefix(), "bin", executable_name)
        if not default_engine_location:
            raise EnvironmentError("Could not find OCC CSG")

        Logger.log("i", "Found Quick CSG at: %s", default_engine_location)
        default_engine_location = os.path.abspath(default_engine_location)
        return [default_engine_location]