import gc
import subprocess
from math import cos, sin
from time import time
from typing import NamedTuple, Optional, List, Union

import numpy
from UM.Application import Application
from UM.Job import Job
from UM.Logger import Logger
from UM.Math.Matrix import Matrix
from UM.Math.Vector import Vector
from UM.Message import Message
from UM.Signal import Signal
from UM.i18n import i18nCatalog

from steslicer.LayerDataBuilder import LayerDataBuilder
from steslicer.LayerPolygon import LayerPolygon
from steslicer.Settings.ExtruderStack import ExtruderStack
from steslicer.SteSlicerApplication import SteSlicerApplication

catalog = i18nCatalog("steslicer")

Position = NamedTuple("Position", [("x", float), ("y", float), ("z", float), (
    "a", float), ("b", float), ("c", float), ("f", Optional[float]), ("e", Optional[List[float]])])

class GenerateBasementJob(Job):
    processingProgress = Signal()
    timeMaterialEstimates = Signal()

    def __init__(self):
        super().__init__()
        self._layer_data_builder = LayerDataBuilder()
        self._abort_requested = False
        self._build_plate_number = None

        self._gcode_list = []
        self._material_amounts = [0.0, 0.0]
        self._times = {
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
        self._position = Position(0, 0, 0, 0, 0, 1, 0, [0])
        self._gcode_position = Position(999, 999, 999, 0, 0, 0, 0, [0])
        self._first_move = True
        self._rot_nwp = Matrix()
        self._rot_nws = Matrix()
        self._pi_faction = 0


        self._global_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        stack = self._global_stack.getTop()
        self._travel_speed = self._global_stack.getProperty(
            "speed_travel", "value")
        self._raft_base_thickness = self._global_stack.getProperty("raft_base_thickness", "value")
        self._raft_base_line_width = self._global_stack.getProperty("raft_base_line_width", "value")
        self._raft_base_line_spacing = self._global_stack.getProperty("raft_base_line_spacing", "value")
        self._raft_speed = self._global_stack.getProperty("raft_speed", "value")
        self._raft_margin = self._global_stack.getProperty("raft_margin", "value")
        self._extruder_number = 0
        self._extruder_offsets = {}
        extruder = self._global_stack.extruders.get("%s" % self._extruder_number, None)  # type: Optional[ExtruderStack]
        self._filament_diameter = extruder.getProperty(
            "material_diameter", "value")

        self._cylindrical_raft_enabled = stack.getProperty("cylindrical_raft_enabled", "value")
        if self._cylindrical_raft_enabled is None:
            self._cylindrical_raft_enabled = self._global_stack.getProperty("cylindrical_raft_enabled", "value")
        self._cylindrical_mode_base_diameter = self._global_stack.getProperty("cylindrical_raft_diameter", "value")
        self._non_printing_base_diameter = self._global_stack.getProperty("non_printing_base_diameter", "value")
        self._cylindrical_raft_base_height = self._global_stack.getProperty("cylindrical_raft_base_height", "value")

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
        self._retraction_speed = self._global_stack.getProperty(
            "retraction_retract_speed", "value")
        self._prime_speed = self._global_stack.getProperty(
            "retraction_prime_speed", "value")

        self._machine_a_axis_coefficient = self._global_stack.getProperty(
            "machine_a_axis_multiplier", "value") / self._global_stack.getProperty(
            "machine_a_axis_divider", "value")
        self._machine_c_axis_coefficient = self._global_stack.getProperty(
            "machine_c_axis_multiplier", "value") / self._global_stack.getProperty(
            "machine_c_axis_divider", "value")

    def abort(self):
        self._abort_requested = True

    def isCancelled(self) -> bool:
        return self._abort_requested

    def setBuildPlate(self, new_value):
        self._build_plate_number = new_value

    def getBuildPlate(self):
        return self._build_plate_number

    def getGCodeList(self):
        return self._gcode_list

    def getLayersData(self):
        return self._layer_data_builder.getLayers().values()

    def getMaterialAmounts(self):
        return self._material_amounts

    def getTimes(self):
        return self._times

    def run(self):
        self._gcode_list = []
        self._material_amounts = [0.0, 0.0]
        self._times = {
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

        Logger.log("d", "Generating basement...")

        if not self._cylindrical_raft_enabled:
            self._gcode_list.append(
                "G0 A0 F600\nG92 E0 C0\n")
            return

        self._position = Position(0, 0, 0, 0, 0, 1, 0, [0])
        self._gcode_position = Position(999, 999, 999, 0, 0, 0, 0, [0])
        self._first_move = True
        current_path = []  # type: List[List[float]]

        layer_count = int((self._cylindrical_mode_base_diameter - self._non_printing_base_diameter) / (2 * self._raft_base_thickness))

        for layer_number in range(0, layer_count):
            if self._abort_requested:
                Logger.log("d", "Parsing basement file cancelled")
                return
            self.processingProgress.emit(layer_number / layer_count)
            self._gcode_list.append(";LAYER:%s\n" % layer_number)

            self._gcode_list[-1] = self.processPolyline(layer_number, current_path, self._gcode_list[-1], layer_count)

            self._createPolygon(layer_number, current_path, self._extruder_offsets.get(
                self._extruder_number, [0, 0]))
            current_path.clear()

            if self._abort_requested:
                return

            Job.yieldThread()

        self._gcode_list.append("G91\nG0 Z50\nG90\nG54\nG0 Z100 A0 F600\nG92 E0 C0\nG1 F200 E-2\nG92 E0 ;zero the extruded length again\nG55\nG1 F200 E2\nG92 E0 ;zero the extruded length again\n")

    def processPolyline(self, layer_number: int, path: List[List[Union[float, int]]], gcode_line: str, layer_count: int) -> str:
        radius = self._non_printing_base_diameter / 2 + (self._raft_base_thickness * (layer_number + 1))
        height = self._cylindrical_raft_base_height - layer_number * self._raft_base_line_width / 3
        if height < self._raft_base_line_width * 2:
            height = self._raft_base_line_width * 2
        points = self._generateHelix(radius, height, layer_number, False)

        new_position, new_gcode_position = points[0]

        is_retraction = self._enable_retraction and self._positionLength(
            self._position, new_position) > self._retraction_min_travel and not self._first_move
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
        self._first_move = False
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

        gcode_line += ";TYPE:SKIRT\n"
        points.pop(0)
        for point in points:
            new_position, new_gcode_position = point
            feedrate = self._raft_speed
            x, y, z, a, b, c, f, e = new_position
            self._position = Position(x, y, z, a, b, c, feedrate, e)
            gcode_command = self._generateGCodeCommand(1, new_gcode_position, feedrate)
            if gcode_command is not None:
                gcode_line += gcode_command
            gx, gy, gz, ga, gb, gc, gf, ge = new_gcode_position
            self._gcode_position = Position(gx, gy, gz, ga, gb, gc, feedrate, ge)
            self._addToPath(path, [x, y, z, a, b, c, feedrate, e, LayerPolygon.SkirtType])
        return gcode_line

    def _generateHelix(self, radius: float, height: float, layer_number: int, reverse_twist: bool,  chordal_err: float = 0.025):
        pitch = self._raft_base_line_width
        max_t = numpy.pi * 2 + height / pitch
        result = []
        position = self._position
        gcode_position = self._gcode_position
        for t in numpy.arange(0, max_t, chordal_err):
            x = radius * cos(t)
            y = radius * (sin(t) if not reverse_twist else -sin(t))
            z = - self._raft_base_line_width / 2 if max_t - t <= (numpy.pi + chordal_err) * 2 else - (height - pitch * t)
            length = numpy.sqrt(x ** 2 + y ** 2)
            i = x / length if length != 0 else 0
            j = y / length if length != 0 else 0
            k = 0
            new_position = Position(x, y, z, i, j, k, 0, [0])
            new_gcode_position = self._transformCoordinates(x, y, z, i, j, k, gcode_position)
            new_position.e[self._extruder_number] = position.e[self._extruder_number] + self._calculateExtrusion(
                [x, y, z],
                position) if t > 0.0 else position.e[self._extruder_number]
            new_gcode_position.e[self._extruder_number] = new_position.e[self._extruder_number]
            position = new_position
            gcode_position = new_gcode_position
            result.append((new_position, new_gcode_position))
        #if layer_number == 0:
        for t in numpy.arange(max_t, 2 * max_t - numpy.pi * 2, chordal_err):
            x = -radius * cos(t - numpy.pi)
            y = radius * (sin(t) if reverse_twist else -sin(t - numpy.pi))
            z = - pitch * (t - max_t)
            length = numpy.sqrt(x ** 2 + y ** 2)
            i = x / length if length != 0 else 0
            j = y / length if length != 0 else 0
            k = 0
            new_position = Position(x, y, z, i, j, k, 0, [0])
            new_gcode_position = self._transformCoordinates(x, y, z, i, j, k, gcode_position)
            new_position.e[self._extruder_number] = position.e[self._extruder_number] + self._calculateExtrusion(
                [x, y, z],
                position) if t > 0.0 else position.e[self._extruder_number]
            new_gcode_position.e[self._extruder_number] = new_position.e[self._extruder_number]
            position = new_position
            gcode_position = new_gcode_position
            result.append((new_position, new_gcode_position))
        return result

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

    def _setByRotationAxis(self, matrix, angle: float, direction: Vector, point: Optional[List[float]] = None) -> None:
        sina = numpy.sin(angle)
        cosa = numpy.cos(angle)
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

    def _calculateExtrusion(self, current_point: List[float], previous_point: Position) -> float:

        Af = (self._filament_diameter / 2) ** 2 * 3.14
        Al = self._raft_base_line_width * self._raft_base_thickness
        de = numpy.sqrt((current_point[0] - previous_point[0])
                        ** 2 + (current_point[1] - previous_point[1]) ** 2 +
                        (current_point[2] - previous_point[2]) ** 2)
        dVe = Al * de
        self._material_amounts[self._extruder_number] += float(dVe)
        return dVe / Af

    def _createPolygon(self, layer_number: int, path: List[List[Union[float, int]]],
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
            self._layer_data_builder.addLayer(layer_number)
            self._layer_data_builder.setLayerHeight(
                layer_number, self._raft_base_thickness * (layer_number + 1))
            self._layer_data_builder.setLayerThickness(
                layer_number, self._raft_base_thickness)
            this_layer = self._layer_data_builder.getLayer(layer_number)
        except ValueError:
            return False
        count = len(path)
        line_types = numpy.empty((count - 1, 1), numpy.int32)
        line_widths = numpy.empty((count - 1, 1), numpy.float32)
        line_thicknesses = numpy.empty((count - 1, 1), numpy.float32)
        line_feedrates = numpy.empty((count - 1, 1), numpy.float32)
        line_widths[:, 0] = self._raft_base_line_width
        line_thicknesses[:, 0] = self._raft_base_thickness
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
                    line_widths[i - 1] = self._raft_base_line_width
            i += 1

        this_poly = LayerPolygon(self._extruder_number, line_types,
                                 points, line_widths, line_thicknesses, line_feedrates)
        this_poly.buildCache()

        this_layer.polygons.append(this_poly)
        return True

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
        self._times[layer_type_to_times_type[layer_type]] += (length / feedrate) * 2
        path.append(addition)

    @staticmethod
    def _positionLength(start: Position, end: Position) -> float:
        return numpy.sqrt((start.x - end.x) ** 2 + (start.y - end.y) ** 2 + (start.z - end.z) ** 2)

    def _generateGCodeCommand(self, g: int, gcode_position: Position, feedrate: float) -> Optional[str]:
        gcode_command = "G%s" % g
        if numpy.abs(gcode_position.x - self._gcode_position.x) > 0.0001:
            gcode_command += " X%.2f" % gcode_position.x
        if numpy.abs(gcode_position.y - self._gcode_position.y) > 0.0001:
            gcode_command += " Y%.2f" % gcode_position.y
        if numpy.abs(gcode_position.z - self._gcode_position.z) > 0.0001:
            gcode_command += " Z%.2f" % gcode_position.z
        if numpy.abs(gcode_position.a - self._gcode_position.a) > 0.0001:
            gcode_command += " A%.2f" % (gcode_position.a * self._machine_a_axis_coefficient)
        if numpy.abs(gcode_position.b - self._gcode_position.b) > 0.0001:
            gcode_command += " B%.2f" % gcode_position.b
        if numpy.abs(gcode_position.c - self._gcode_position.c) > 0.0001:
            gcode_command += " C%.3f" % (gcode_position.c * self._machine_c_axis_coefficient)
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