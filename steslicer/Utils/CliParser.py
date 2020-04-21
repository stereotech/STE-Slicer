import io
from time import time
from math import radians
from typing import Dict, List, NamedTuple, Optional, Union
import re
import math
import numpy
from UM.Application import Application
from UM.Mesh.MeshData import MeshData
from UM.View.GL.OpenGLContext import OpenGLContext

from steslicer.Scene.BuildPlateDecorator import BuildPlateDecorator
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode

from UM.Logger import Logger
from UM.Job import Job
from UM.Signal import Signal
from UM.Message import Message

from steslicer.Settings.ExtrudersModel import ExtrudersModel
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.LayerDataBuilder import LayerDataBuilder
from steslicer.LayerDataDecorator import LayerDataDecorator
from steslicer.LayerPolygon import LayerPolygon
from steslicer.Scene.GCodeListDecorator import GCodeListDecorator
from steslicer.Settings.ExtruderManager import ExtruderManager
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Backend import Backend
from UM.Math.Vector import Vector
from math import degrees
from UM.Math.Matrix import Matrix

from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.InstanceContainer import InstanceContainer
from steslicer.Settings.GlobalStack import GlobalStack
from steslicer.Settings.ExtruderStack import ExtruderStack

CliPoint = NamedTuple(
    "CliPoint", [("x", Optional[float]), ("y", Optional[float])])
Position = NamedTuple("Position", [("x", float), ("y", float), ("z", float), (
    "a", float), ("b", float), ("c", float), ("f", Optional[float]), ("e", Optional[List[float]])])

class CliParser:
    progressChanged = Signal()
    timeMaterialEstimates = Signal()
    layersDataGenerated = Signal()

    def __init__(self, build_plate_number) -> None:
        self._profiled = False
        self._material_amounts = [0, 0]

        self._time_estimates = {
            "inset_0": 0,
            "inset_x": 0,
            "skin": 0,
            "infill": 0,
            "support_infill": 0,
            "support_interface": 0,
            "support": 0,
            "skirt": 0,
            "travel": 0,
            "retract": 0,
            "none": 0
        }

        self._build_plate_number = build_plate_number
        self._is_layers_in_file = False
        self._cancelled = False
        # self._message = None
        self._layer_number = -1
        self._extruder_number = 0
        self._pi_faction = 0
        self._position = Position
        self._gcode_position = Position
        # stack to get print settingd via getProperty method
        self._application = SteSlicerApplication.getInstance()
        self._global_stack = self._application.getGlobalContainerStack()  # type: GlobalStack
        self._licensed = self._application.getLicenseManager().licenseValid

        self._rot_nwp = Matrix()
        self._rot_nws = Matrix()

        self._scene_node = None
        self._layer_type = LayerPolygon.Inset0Type
        self._extruder_number = 0
        # type: Dict[int, List[float]] # Offsets for multi extruders. key is index, value is [x-offset, y-offset]
        self._extruder_offsets = {}

        self._gcode_list = []

        self._current_layer_thickness = 0
        self._current_layer_height = 0

        # speeds
        self._travel_speed = 0
        self._wall_0_speed = 0
        self._skin_speed = 0
        self._infill_speed = 0
        self._support_speed = 0
        self._retraction_speed = 0
        self._prime_speed = 0

        # retraction
        self._enable_retraction = False
        self._retraction_amount = 0
        self._retraction_min_travel = 1.5
        self._retraction_hop_enabled = False
        self._retraction_hop = 1

        self._filament_diameter = 1.75
        self._line_width = 0.4
        self._layer_thickness = 0.2
        self._clearValues()

    _layer_keyword = "$$LAYER/"
    _geometry_end_keyword = "$$GEOMETRYEND"
    _body_type_keyword = "//body//"
    _support_type_keyword = "//support//"
    _skin_type_keyword = "//skin//"
    _infill_type_keyword = "//infill//"
    _perimeter_type_keyword = "//perimeter//"

    _type_keyword = ";TYPE:"

    def cancel(self):
        self._cancelled = True

    def getLayersData(self):
        if self._layer_data_builder:
            return self._layer_data_builder.getLayers()
        else:
            return []

    def getMaterialAmounts(self):
        return self._material_amounts

    def getTimes(self):
        return self._time_estimates

    def processCliStream(self, stream: str) -> List[str]:
        Logger.log("d", "Preparing to load CLI")
        start_time = time()
        self._cancelled = False
        self._setPrintSettings()
        self._is_layers_in_file = False

        self._gcode_list = []

        self._writeStartCode(self._gcode_list)
        self._gcode_list[-1] += ";LAYER_COUNT\n"

        # Reading starts here
        file_lines = 0
        current_line = 0
        for line in stream.split("\n"):
            file_lines += 1
            if not self._is_layers_in_file and line[:len(self._layer_keyword)] == self._layer_keyword:
                self._is_layers_in_file = True

        file_step = max(math.floor(file_lines / 100), 1)

        self._clearValues()
        self.progressChanged.emit(0)

        Logger.log("d", "Parsing CLI...")

        self._position = Position(0, 0, 0, 0, 0, 1, 0, [0])
        self._gcode_position = Position(999, 999, 999, 0, 0, 0, 0, [0])
        current_path = []  # type: List[List[float]]
        geometry_start = False

        for line in stream.split("\n"):
            if self._cancelled:
                Logger.log("d", "Parsing CLI file cancelled")
                return None
            current_line += 1
            if current_line % file_step == 0:
                self.progressChanged.emit(math.floor(
                    current_line / file_lines * 100))
                Job.yieldThread()
            if len(line) == 0:
                continue
            if line == "$$GEOMETRYSTART":
                geometry_start = True
                continue
            if not geometry_start:
                continue

            if self._is_layers_in_file and line[:len(self._layer_keyword)] == self._layer_keyword:
                try:
                    layer_height = float(line[len(self._layer_keyword):])
                    self._current_layer_thickness = layer_height - self._current_layer_height
                    if self._current_layer_thickness > 0.4:
                        self._current_layer_thickness = 0.2
                    self._current_layer_height = layer_height
                    self._createPolygon(self._current_layer_thickness, current_path, self._extruder_offsets.get(
                        self._extruder_number, [0, 0]))
                    current_path.clear()

                    # Start the new layer at the end position of the last layer
                    self._addToPath(current_path,
                                    [self._position.x, self._position.y, self._position.z, self._position.a,
                                     self._position.b,
                                     self._position.c, self._position.f, self._position.e[self._extruder_number],
                                     LayerPolygon.MoveCombingType])
                    # current_path.append(
                    #    [self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
                    #     self._position.c, self._position.f, self._position.e[self._extruder_number],
                    #     LayerPolygon.MoveCombingType])
                    if not (self._gcode_list[-1].startswith(";LAYER:") and self._gcode_list[-1].count('\n') < 2):
                        self._layer_number += 1
                        self._gcode_list.append(";LAYER:%s\n" % self._layer_number)
                except:
                    pass

            if line.find(self._body_type_keyword) == 0:
                self._layer_type = LayerPolygon.Inset0Type
            if line.find(self._support_type_keyword) == 0:
                self._layer_type = LayerPolygon.SupportType
            if line.find(self._perimeter_type_keyword) == 0:
                self._layer_type = LayerPolygon.Inset0Type
            if line.find(self._skin_type_keyword) == 0:
                self._layer_type = LayerPolygon.SkinType
            if line.find(self._infill_type_keyword) == 0:
                self._layer_type = LayerPolygon.InfillType

            # Comment line
            if line.startswith("//"):
                continue

            # Polyline processing
            self._gcode_list[-1] = self.processPolyline(line, current_path, self._gcode_list[-1])

            if self._cancelled:
                return None

        # "Flush" leftovers. Last layer paths are still stored
        if len(current_path) > 1:
            if self._createPolygon(self._current_layer_thickness, current_path,
                                   self._extruder_offsets.get(self._extruder_number, [0, 0])):
                self._layer_number += 1
                current_path.clear()

        self._gcode_list[0].replace(";LAYER_COUNT:\n", ";LAYER_COUNT:%s\n" % self._layer_number)

        end_gcode = self._global_stack.getProperty(
            "machine_end_gcode", "value")
        self._gcode_list.append(end_gcode + "\n")

        self.timeMaterialEstimates.emit(self._material_amounts, self._time_estimates)
        self.layersDataGenerated.emit(self._layer_data_builder.getLayers())

        return self._gcode_list

    def _setPrintSettings(self):
        pass

    def _onHideMessage(self, message: Optional[Union[str, Message]]) -> None:
        if message == self._message:
            self._cancelled = True

    def _clearValues(self):
        self._material_amounts = [0.0, 0.0]
        self._time_estimates = {
            "inset_0": 60,
            "inset_x": 0,
            "skin": 0,
            "infill": 0,
            "support_infill": 0,
            "support_interface": 0,
            "support": 0,
            "skirt": 0,
            "travel": 0,
            "retract": 0,
            "none": 0
        }
        self._extruder_number = 0
        self._layer_number = -1
        self._layer_data_builder = LayerDataBuilder()
        self._pi_faction = 0
        self._position = Position(0, 0, 0, 0, 0, 1, 0, [0])
        self._gcode_position = Position(0, 0, 0, 0, 0, 0, 0, [0])
        self._rot_nwp = Matrix()
        self._rot_nws = Matrix()
        self._layer_type = LayerPolygon.Inset0Type

        self._parsing_type = self._global_stack.getProperty(
            "printing_mode", "value")
        self._line_width = self._global_stack.getProperty("wall_line_width_0", "value")
        self._layer_thickness = self._global_stack.getProperty("layer_height", "value")

        self._travel_speed = self._global_stack.getProperty(
            "speed_travel", "value")
        self._wall_0_speed = self._global_stack.getProperty(
            "speed_wall_0", "value")
        self._skin_speed = self._global_stack.getProperty(
            "speed_topbottom", "value")
        self._infill_speed = self._global_stack.getProperty("speed_infill", "value")
        self._support_speed = self._global_stack.getProperty(
            "speed_support", "value")
        self._retraction_speed = self._global_stack.getProperty(
            "retraction_retract_speed", "value")
        self._prime_speed = self._global_stack.getProperty(
            "retraction_prime_speed", "value")

        extruder = self._global_stack.extruders.get("%s" % self._extruder_number, None)  # type: Optional[ExtruderStack]

        self._filament_diameter = extruder.getProperty(
            "material_diameter", "value")
        self._enable_retraction = extruder.getProperty(
            "retraction_enable", "value")
        self._retraction_amount = extruder.getProperty(
            "retraction_amount", "value")
        self._retraction_min_travel = extruder.getProperty(
            "retraction_min_travel", "value")
        self._retraction_hop_enabled = extruder.getProperty(
            "retraction_hop_enabled", "value")
        self._retraction_hop = extruder.getProperty(
            "retraction_hop", "value")

    def _setByRotationAxis(self, matrix, angle: float, direction: Vector, point: Optional[List[float]] = None) -> None:
        sina = math.sin(angle)
        cosa = math.cos(angle)
        direction_data = matrix._unitVector(direction.getData())
        # rotation matrix around unit vector
        R = numpy.diag([cosa, cosa, cosa])
        R += numpy.outer(direction_data, direction_data) * (1.0 - cosa)
        direction_data *= sina
        R += numpy.array([[0.0, -direction_data[2], direction_data[1]],
                          [direction_data[2], 0.0, -direction_data[0]],
                          [-direction_data[1], direction_data[0], 0.0]], dtype=numpy.float64)
        M = numpy.identity(4)
        M[:3, :3] = R
        if point is not None:
            # rotation not around origin
            point = numpy.array(point[:3], dtype=numpy.float64, copy=False)
            M[:3, 3] = point - numpy.dot(R, point)
        matrix._data = M

    def _transformCoordinates(self, x: float, y: float, z: float, i: float, j: float, k: float, position: Position) -> (
            float, float, float, float, float, float):
        a = position.a
        c = position.c
        # Get coordinate angles
        if abs(self._position.c - k) > 0.00001:
            a = numpy.arccos(k)
            self._rot_nwp = Matrix()
            self._setByRotationAxis(self._rot_nwp, -a, Vector.Unit_X)
            # self._rot_nwp.setByRotationAxis(-a, Vector.Unit_X)
            a = numpy.degrees(a)
        if abs(self._position.a - i) > 0.00001 or abs(self._position.b - j) > 0.00001:
            c = numpy.arctan2(j, i) if x != 0 and y != 0 else 0
            angle = numpy.degrees(c + self._pi_faction * 2 * numpy.pi)
            if abs(angle - position.c) > 180:
                self._pi_faction += 1 if (angle - position.c) < 0 else -1
            c += self._pi_faction * 2 * numpy.pi
            c -= numpy.pi / 2
            self._rot_nws = Matrix()
            self._setByRotationAxis(self._rot_nws, c, Vector.Unit_Z)
            # self._rot_nws.setByRotationAxis(c, Vector.Unit_Z)
            c = numpy.degrees(c)

        tr = self._rot_nws.multiply(self._rot_nwp, True)
        tr.invert()
        pt = Vector(data=numpy.array([x, y, z, 1]))
        ret = tr.multiply(pt, True).getData()

        return Position(ret[0], ret[1], ret[2], a, 0, c, 0, [0])

    @staticmethod
    def _getValue(line: str, key: str) -> Optional[str]:
        n = line.find(key)
        if n < 0:
            return None
        n += len(key)
        splitted = line[n:].split("/")
        if len(splitted) > 1:
            return splitted[1]
        else:
            return None

    def _createPolygon(self, layer_thickness: float, path: List[List[Union[float, int]]],
                       extruder_offsets: List[float]) -> bool:
        countvalid = 0
        for point in path:
            if point[8] > 0:
                countvalid += 1
                if countvalid >= 2:
                    # we know what to do now, no need to count further
                    continue
        if countvalid < 2:
            return False
        try:
            self._layer_data_builder.addLayer(self._layer_number)
            self._layer_data_builder.setLayerHeight(
                self._layer_number, self._current_layer_height)
            self._layer_data_builder.setLayerThickness(
                self._layer_number, layer_thickness)
            this_layer = self._layer_data_builder.getLayer(self._layer_number)
        except ValueError:
            return False
        count = len(path)
        line_types = numpy.empty((count - 1, 1), numpy.int32)
        line_widths = numpy.empty((count - 1, 1), numpy.float32)
        line_thicknesses = numpy.empty((count - 1, 1), numpy.float32)
        line_feedrates = numpy.empty((count - 1, 1), numpy.float32)
        line_widths[:, 0] = 0.35  # Just a guess
        line_thicknesses[:, 0] = layer_thickness
        points = numpy.empty((count, 6), numpy.float32)
        extrusion_values = numpy.empty((count, 1), numpy.float32)
        i = 0
        for point in path:

            points[i, :] = [point[0] + extruder_offsets[0], point[2], -point[1] - extruder_offsets[1],
                            -point[4], point[5], -point[3]]
            extrusion_values[i] = point[7]
            if i > 0:
                line_feedrates[i - 1] = point[6]
                line_types[i - 1] = point[8]
                if point[8] in [LayerPolygon.MoveCombingType, LayerPolygon.MoveRetractionType]:
                    line_widths[i - 1] = 0.1
                    # Travels are set as zero thickness lines
                    line_thicknesses[i - 1] = 0.0
                else:
                    line_widths[i - 1] = self._line_width
            i += 1

        this_poly = LayerPolygon(self._extruder_number, line_types,
                                 points, line_widths, line_thicknesses, line_feedrates)
        this_poly.buildCache()

        this_layer.polygons.append(this_poly)
        return True

    def processPolyline(self, line: str, path: List[List[Union[float, int]]], gcode_line: str) -> str:
        # Convering line to point array
        values_line = self._getValue(line, "$$POLYLINE")
        if not values_line:
            return gcode_line
        values = values_line.split(",")
        if len(values[3:]) % 2 != 0:
            return gcode_line
        idx = 2
        points = values[3:]
        if len(points) < 2:
            return gcode_line
        # TODO: add combing to this polyline
        new_position, new_gcode_position = self._cliPointToPosition(
            CliPoint(float(points[0]), float(points[1])), self._position, False)

        is_retraction = self._enable_retraction and self._positionLength(
            self._position, new_position) > self._retraction_min_travel and self._layer_type not in [
            LayerPolygon.InfillType, LayerPolygon.SupportType]
        if is_retraction:
            # we have retraction move
            new_extruder_position = self._position.e[self._extruder_number] - self._retraction_amount
            gcode_line += "G1 E%.5f F%.0f\n" % (new_extruder_position, (self._retraction_speed * 60))
            self._position.e[self._extruder_number] = new_extruder_position
            self._gcode_position.e[self._extruder_number] = new_extruder_position
            self._addToPath(path,
                            [self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
                             self._position.c, self._retraction_speed, self._position.e,
                             LayerPolygon.MoveRetractionType])
            # path.append([self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
            #             self._position.c, self._retraction_speed, self._position.e, LayerPolygon.MoveRetractionType])

            if self._retraction_hop_enabled:
                # add hop movement
                gx, gy, gz, ga, gb, gc, gf, ge = self._gcode_position
                x, y, z, a, b, c, f, e = self._position
                gcode_position = Position(
                    gx, gy, gz + self._retraction_hop, ga, gb, gc, self._travel_speed, ge)
                self._position = Position(
                    x + a * self._retraction_hop, y + b * self._retraction_hop, z + c * self._retraction_hop, a, b, c,
                    self._travel_speed, e)
                gcode_command = self._generateGCodeCommand(
                    0, gcode_position, self._travel_speed)
                if gcode_command is not None:
                    gcode_line += gcode_command
                self._gcode_position = gcode_position
                self._addToPath(path, [self._position.x, self._position.y, self._position.z, self._position.a,
                                       self._position.b,
                                       self._position.c, self._prime_speed, self._position.e,
                                       LayerPolygon.MoveCombingType])
                # path.append([self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
                #             self._position.c, self._prime_speed, self._position.e, LayerPolygon.MoveCombingType])
                gx, gy, gz, ga, gb, gc, gf, ge = new_gcode_position
                x, y, z, a, b, c, f, e = new_position
                gcode_position = Position(
                    gx, gy, gz + self._retraction_hop, ga, gb, gc, self._travel_speed, ge)
                position = Position(
                    x + a * self._retraction_hop, y + b * self._retraction_hop, z + c * self._retraction_hop, a, b, c,
                    self._travel_speed, e)
                gcode_command = self._generateGCodeCommand(
                    0, gcode_position, self._travel_speed)
                if gcode_command is not None:
                    gcode_line += gcode_command
                self._addToPath(path, [position.x, position.y, position.z, position.a, position.b,
                                       position.c, position.f, position.e, LayerPolygon.MoveCombingType])
                # path.append([position.x, position.y, position.z, position.a, position.b,
                #             position.c, position.f, position.e, LayerPolygon.MoveCombingType])

        feedrate = self._travel_speed
        x, y, z, a, b, c, f, e = new_position
        self._position = Position(x, y, z, a, b, c, feedrate, self._position.e)
        gcode_command = self._generateGCodeCommand(0, new_gcode_position, feedrate)
        if gcode_command is not None:
            gcode_line += gcode_command
        gx, gy, gz, ga, gb, gc, gf, ge = new_gcode_position
        self._gcode_position = Position(gx, gy, gz, ga, gb, gc, feedrate, ge)
        self._addToPath(path, [x, y, z, a, b, c, feedrate, e,
                               LayerPolygon.MoveCombingType])
        # path.append([x, y, z, a, b, c, feedrate, e,
        #             LayerPolygon.MoveCombingType])

        if is_retraction:
            # we have retraction move
            new_extruder_position = self._position.e[self._extruder_number] + self._retraction_amount
            gcode_line += "G1 E%.5f F%.0f\n" % (new_extruder_position, (self._prime_speed * 60))
            self._position.e[self._extruder_number] = new_extruder_position
            self._gcode_position.e[self._extruder_number] = new_extruder_position
            self._addToPath(path,
                            [self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
                             self._position.c, self._prime_speed, self._position.e, LayerPolygon.MoveRetractionType])
            # path.append([self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
            #             self._position.c, self._prime_speed, self._position.e, LayerPolygon.MoveRetractionType])

        if self._layer_type == LayerPolygon.SupportType:
            gcode_line += self._type_keyword + "SUPPORT\n"
        elif self._layer_type == LayerPolygon.SkinType:
            gcode_line += self._type_keyword + "SKIN\n"
        elif self._layer_type == LayerPolygon.InfillType:
            gcode_line += self._type_keyword + "FILL\n"
        else:
            gcode_line += self._type_keyword + "WALL-OUTER\n"

        while idx < len(points):
            point = CliPoint(float(points[idx]), float(points[idx + 1]))
            idx += 2
            new_position, new_gcode_position = self._cliPointToPosition(point, self._position)
            feedrate = self._wall_0_speed
            if self._layer_type == LayerPolygon.SupportType:
                feedrate = self._support_speed
            elif self._layer_type == LayerPolygon.SkinType:
                feedrate = self._skin_speed
            elif self._layer_type == LayerPolygon.InfillType:
                feedrate = self._infill_speed
            x, y, z, a, b, c, f, e = new_position
            self._position = Position(x, y, z, a, b, c, feedrate, e)
            gcode_command = self._generateGCodeCommand(1, new_gcode_position, feedrate)
            if gcode_command is not None:
                gcode_line += gcode_command
            gx, gy, gz, ga, gb, gc, gf, ge = new_gcode_position
            self._gcode_position = Position(gx, gy, gz, ga, gb, gc, feedrate, ge)
            self._addToPath(path, [x, y, z, a, b, c, feedrate, e, self._layer_type])
            # path.append([x, y, z, a, b, c, feedrate, e, self._layer_type])
        return gcode_line

    def _generateGCodeCommand(self, g: int, gcode_position: Position, feedrate: float) -> Optional[str]:
        gcode_command = "G%s" % g
        if numpy.abs(gcode_position.x - self._gcode_position.x) > 0.0001:
            gcode_command += " X%.2f" % gcode_position.x
        if numpy.abs(gcode_position.y - self._gcode_position.y) > 0.0001:
            gcode_command += " Y%.2f" % gcode_position.y
        if numpy.abs(gcode_position.z - self._gcode_position.z) > 0.0001:
            gcode_command += " Z%.2f" % gcode_position.z
        if numpy.abs(gcode_position.a - self._gcode_position.a) > 0.0001:
            gcode_command += " A%.2f" % gcode_position.a
        if numpy.abs(gcode_position.b - self._gcode_position.b) > 0.0001:
            gcode_command += " B%.2f" % gcode_position.b
        if numpy.abs(gcode_position.c - self._gcode_position.c) > 0.0001:
            gcode_command += " C%.2f" % gcode_position.c
        if numpy.abs(feedrate - self._gcode_position.f) > 0.0001:
            gcode_command += " F%.0f" % (feedrate * 60)
        if numpy.abs(gcode_position.e[self._extruder_number] - self._gcode_position.e[
            self._extruder_number]) > 0.0001 and g > 0:
            gcode_command += " E%.5f" % gcode_position.e[self._extruder_number]
        gcode_command += "\n"
        if gcode_command != "G%s\n" % g:
            return gcode_command
        else:
            return None

    def _calculateExtrusion(self, current_point: List[float], previous_point: Position) -> float:

        Af = (self._filament_diameter / 2) ** 2 * 3.14
        Al = self._line_width * self._layer_thickness
        de = numpy.sqrt((current_point[0] - previous_point[0])
                        ** 2 + (current_point[1] - previous_point[1]) ** 2 +
                        (current_point[2] - previous_point[2]) ** 2)
        dVe = Al * de
        self._material_amounts[self._extruder_number] += float(dVe)
        return dVe / Af

    def _writeStartCode(self, gcode_list: List[str]):
        if self._parsing_type == "cylindrical":
            start_gcode = "T0\n"
            extruder = self._global_stack.extruders.get("%s" % self._extruder_number, None)  # type: Optional[ExtruderStack]
            init_temperature = extruder.getProperty(
                "material_print_temperature", "value")
            init_bed_temperature = extruder.getProperty(
                "material_bed_temperature", "value")
            has_heated_bed = self._global_stack.getProperty("machine_heated_bed", "value")
            if has_heated_bed:
                start_gcode += "M140 S%s\n" % init_bed_temperature
                start_gcode += "M105\n"
                start_gcode += "M190 S%s\n" % init_bed_temperature
            start_gcode +="M104 S%s\n" % init_temperature
            start_gcode += "M105\n"
            start_gcode += "M109 S%s\n" % init_temperature
            start_gcode += "M82 ;absolute extrusion mode\n"
            start_gcode_prefix = self._global_stack.getProperty(
                "machine_start_gcode", "value")
            if self._parsing_type in ["cylindrical", "cylindrical_full"]:
                start_gcode_prefix = start_gcode_prefix.replace("G55", "G56")
            start_gcode += start_gcode_prefix
            gcode_list.append(start_gcode + "\n")
        elif self._parsing_type == "cylindrical_full":
            gcode_list.append("G54\nG0 Z125 A90 F600\nG92 E0 C0\nG1 F200 E-1 ;retract 1 mm of feed stock\nG92 E0 ;zero the extruded length again\nG56\nG1 F200 E1 ;extrude 1 mm of feed stock\nG92 E0 ;zero the extruded length again\n")
        else:
            gcode_list.append("G54\nG0 Z125 A90 F600\nG92 E0 C0\nG1 F200 E6 ;extrude 6 mm of feed stock\nG92 E0 ;zero the extruded length again\nG56\n")

    def _cliPointToPosition(self, point: CliPoint, position: Position, extrusion_move: bool = True) -> (
            Position, Position):
        x, y, z, i, j, k = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        if self._parsing_type == "classic":
            x = point.x
            y = point.y
            z = self._current_layer_height
            i = 0
            j = 0
            k = 1
        elif self._parsing_type in ["cylindrical", "cylindrical_full"]:
            x = self._current_layer_height * math.cos(point.y)
            y = self._current_layer_height * math.sin(point.y)
            z = point.x
            length = numpy.sqrt(x ** 2 + y ** 2)
            i = x / length if length != 0 else 0
            j = y / length if length != 0 else 0
            k = 0
        new_position = Position(x, y, z, i, j, k, 0, [0])

        new_gcode_position = self._transformCoordinates(x, y, z, i, j, k, self._gcode_position)
        new_position.e[self._extruder_number] = position.e[self._extruder_number] + self._calculateExtrusion([x, y, z],
                                                                                                             position) if extrusion_move else \
            position.e[self._extruder_number]
        new_gcode_position.e[self._extruder_number] = new_position.e[self._extruder_number]

        return new_position, new_gcode_position

    @staticmethod
    def _positionLength(start: Position, end: Position) -> float:
        return numpy.sqrt((start.x - end.x) ** 2 + (start.y - end.y) ** 2 + (start.z - end.z) ** 2)

    def _addToPath(self, path: List[List[Union[float, int]]], addition: List[Union[float, int]]):
        layer_type = addition[8]
        layer_type_to_times_type = {
            LayerPolygon.NoneType: "none",
            LayerPolygon.Inset0Type: "inset_0",
            LayerPolygon.InsetXType: "inset_x",
            LayerPolygon.SkinType: "skin",
            LayerPolygon.SupportType: "support",
            LayerPolygon.SkirtType: "skirt",
            LayerPolygon.InfillType: "infill",
            LayerPolygon.SupportInfillType: "support_infill",
            LayerPolygon.MoveCombingType: "travel",
            LayerPolygon.MoveRetractionType: "retract",
            LayerPolygon.SupportInterfaceType: "support_interface"
        }
        if len(path) > 0:
            last_point = path[-1]
        else:
            last_point = addition
        length = numpy.sqrt((last_point[0] - addition[0]) ** 2 + (last_point[1] - addition[1]) ** 2 + (
                    last_point[2] - addition[2]) ** 2)
        feedrate = addition[6]
        if feedrate == 0:
            feedrate = self._travel_speed
        self._time_estimates[layer_type_to_times_type[layer_type]] += (length / feedrate) * 2
        path.append(addition)
