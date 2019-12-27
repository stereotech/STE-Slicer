from math import radians
from typing import Dict, List, NamedTuple, Optional, Union
import re
import math
import numpy
from cura.Scene.CuraSceneNode import CuraSceneNode

from UM.Logger import Logger
from UM.Job import Job
from UM.Message import Message
from UM.i18n import i18nCatalog
from cura.CuraApplication import CuraApplication
from cura.LayerDataBuilder import LayerDataBuilder
from cura.LayerDataDecorator import LayerDataDecorator
from cura.LayerPolygon import LayerPolygon
from cura.Scene.GCodeListDecorator import GCodeListDecorator
from cura.Settings.ExtruderManager import ExtruderManager
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Backend import Backend
from UM.Math.Vector import Vector
from math import degrees
from UM.Math.Matrix import Matrix

from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.InstanceContainer import InstanceContainer
from cura.Settings.GlobalStack import GlobalStack
from cura.Settings.ExtruderStack import ExtruderStack

catalog = i18nCatalog("cura")


CliPoint = NamedTuple(
    "CliPoint", [("x", Optional[float]), ("y", Optional[float])])
Position = NamedTuple("Position", [("x", float), ("y", float), ("z", float), (
    "a", float), ("b", float), ("c", float), ("f", Optional[float]), ("e", Optional[List[float]])])


class CliParser:

    def __init__(self) -> None:
        CuraApplication.getInstance().hideMessageSignal.connect(self._onHideMessage)
        self._is_layers_in_file = False
        self._cancelled = False
        self._message = None
        self._layer_number = -1
        self._extruder_number = 0
        self._pi_faction = 0
        self._position = Position
        self._gcode_position = Position
        # stack to get print settingd via getProperty method
        self._application = CuraApplication.getInstance()
        self._global_stack = self._application.getGlobalContainerStack() #type: GlobalStack

        self._rot_nwp = Matrix()
        self._rot_nws = Matrix()

        self._scene_node = None
        
        self._extruder_number = 0
        # type: Dict[int, List[float]] # Offsets for multi extruders. key is index, value is [x-offset, y-offset]
        self._extruder_offsets = {}
        self._gcode_list = []
        self._current_layer_thickness = 0
        self._current_layer_height = 0

        #speeds
        self._travel_speed = 0
        self._wall_0_speed = 0
        self._skin_speed = 0
        self._infill_speed = 0
        self._support_speed = 0
        self._retraction_speed = 0
        self._prime_speed = 0

        #retraction
        self._enable_retraction = False
        self._retraction_amount = 0
        self._retraction_min_travel = 1.5

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

    def processCliStream(self, stream: str) -> Optional[CuraSceneNode]:
        Logger.log("d", "Preparing to load CLI")
        self._cancelled = False
        self._setPrintSettings()
        self._is_layers_in_file = False

        scene_node = CuraSceneNode()

        gcode_list = []
        self._writeStartCode(gcode_list)
        gcode_list.append(";LAYER_COUNT\n")

        # Reading starts here
        file_lines = 0
        current_line = 0
        for line in stream.split("\n"):
            file_lines += 1
            if not self._is_layers_in_file and line[:len(self._layer_keyword)] == self._layer_keyword:
                self._is_layers_in_file = True

        file_step = max(math.floor(file_lines / 100), 1)

        self._clearValues()

        self._message = Message(catalog.i18nc("@info:status", "Parsing CLI"),
                                lifetime=0,
                                title=catalog.i18nc("@info:title", "CLI Details"))

        assert(self._message is not None)  # use for typing purposes
        self._message.setProgress(0)
        self._message.show()

        Logger.log("d", "Parsing CLI...")

        self._position = Position(0, 0, 0, 0, 0, 1, 0, [0])
        self._gcode_position = Position(0, 0, 0, 0, 0, 0, 0, [0])
        current_path = []  # type: List[List[float]]
        geometry_start = False
        for line in stream.split("\n"):
            if self._cancelled:
                Logger.log("d", "Parsing CLI file cancelled")
                return None
            current_line += 1
            if current_line % file_step == 0:
                self._message.setProgress(math.floor(
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
                    current_path.append([self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
                                         self._position.c, self._position.f, self._position.e[self._extruder_number], LayerPolygon.MoveCombingType])
                    self._layer_number += 1
                    gcode_list.append(";LAYER:%s\n" % self._layer_number)
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
            self.processPolyline(line, current_path, gcode_list)

        # "Flush" leftovers. Last layer paths are still stored
        if len(current_path) > 1:
            if self._createPolygon(self._current_layer_thickness, current_path, self._extruder_offsets.get(self._extruder_number, [0, 0])):
                self._layer_number += 1
                current_path.clear()

        layer_count_idx = gcode_list.index(";LAYER_COUNT\n")
        if layer_count_idx > 0:
            gcode_list[layer_count_idx] = ";LAYER_COUNT:%s\n" % self._layer_number

        end_gcode = self._global_stack.getProperty(
            "machine_end_gcode", "value")
        gcode_list.append(end_gcode + "\n")
        
        material_color_map = numpy.zeros((8, 4), dtype=numpy.float32)
        material_color_map[0, :] = [0.0, 0.7, 0.9, 1.0]
        material_color_map[1, :] = [0.7, 0.9, 0.0, 1.0]
        material_color_map[2, :] = [0.9, 0.0, 0.7, 1.0]
        material_color_map[3, :] = [0.7, 0.0, 0.0, 1.0]
        material_color_map[4, :] = [0.0, 0.7, 0.0, 1.0]
        material_color_map[5, :] = [0.0, 0.0, 0.7, 1.0]
        material_color_map[6, :] = [0.3, 0.3, 0.3, 1.0]
        material_color_map[7, :] = [0.7, 0.7, 0.7, 1.0]
        layer_mesh = self._layer_data_builder.build(material_color_map)
        decorator = LayerDataDecorator()
        decorator.setLayerData(layer_mesh)
        scene_node.addDecorator(decorator)

        gcode_list_decorator = GCodeListDecorator()
        gcode_list_decorator.setGCodeList(gcode_list)
        scene_node.addDecorator(gcode_list_decorator)

        # gcode_dict stores gcode_lists for a number of build plates.
        active_build_plate_id = CuraApplication.getInstance(
        ).getMultiBuildPlateModel().activeBuildPlate
        gcode_dict = {active_build_plate_id: gcode_list}
        # type: ignore #Because gcode_dict is generated dynamically.
        CuraApplication.getInstance().getController().getScene().gcode_dict = gcode_dict

        Logger.log("d", "Finished parsing CLI file")
        self._message.hide()

        if self._layer_number == 0:
            Logger.log("w", "File doesn't contain any valid layers")

        if not self._global_stack.getProperty("machine_center_is_zero", "value"):
            machine_width = self._global_stack.getProperty(
                "machine_width", "value")
            machine_depth = self._global_stack.getProperty(
                "machine_depth", "value")
            scene_node.setPosition(
                Vector(-machine_width / 2, 0, machine_depth / 2))

        Logger.log("d", "CLI loading finished")

        if CuraApplication.getInstance().getPreferences().getValue("gcodereader/show_caution"):
            caution_message = Message(catalog.i18nc(
                "@info:generic",
                "Make sure the g-code is suitable for your printer and printer configuration before sending the file to it. The g-code representation may not be accurate."),
                lifetime=0,
                title=catalog.i18nc("@info:title", "G-code Details"))
            caution_message.show()

        backend = CuraApplication.getInstance().getBackend()
        backend.backendStateChange.emit(Backend.BackendState.Disabled)

        return scene_node

    def _setPrintSettings(self):
        pass

    def _onHideMessage(self, message: str) -> None:
        if message == self._message:
            self._cancelled = True

    def _clearValues(self):
        self._extruder_number = 0
        self._layer_number = -1
        self._layer_data_builder = LayerDataBuilder()
        self._pi_faction = 0
        self._position = Position(0,0,0,0,0,1,0,[0])
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

        extruder = self._global_stack.extruders.get("%s" % self._extruder_number, None) #type: Optional[ExtruderStack]
        
        self._filament_diameter = extruder.getProperty(
            "material_diameter", "value")
        self._enable_retraction = extruder.getProperty(
            "retraction_enable", "value")
        self._retraction_amount = extruder.getProperty(
            "retraction_amount", "value")
        self._retraction_min_travel = extruder.getProperty(
            "retraction_min_travel", "value")

    def _transformCoordinates(self, x: float, y: float, z: float, i: float, j: float, k: float, position: Position) -> (float, float, float, float, float, float):
        a = position.a
        c = position.c
        y_matrix = Matrix()
        y_matrix.setByRotationAxis(math.pi, Vector.Unit_Y)
        # Get coordinate angles
        if abs(self._position.c - k) > 0.00001:
            a = math.acos(k)
            self._rot_nwp = Matrix()
            self._rot_nwp.setByRotationAxis(-a, Vector.Unit_X)
            a = degrees(a)
        if abs(self._position.a - i) > 0.00001 or abs(self._position.b - j) > 0.00001:
            c = numpy.arctan2(j, i) if x != 0 and y != 0 else 0
            angle = degrees(c + self._pi_faction * 2 * math.pi)
            if abs(angle - position.c) > 180:
                self._pi_faction += 1 if (angle - position.c) < 0 else -1
            c += self._pi_faction * 2 * math.pi
            c += math.pi / 2
            self._rot_nws = Matrix()
            self._rot_nws.setByRotationAxis(c, Vector.Unit_Z)
            c = degrees(c)
        
        #tr = self._rot_nws.multiply(self._rot_nwp, True)
        tr = self._rot_nws.multiply(self._rot_nwp, True)
        #tr = tr.multiply(self._rot_nwp)
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

    def _createPolygon(self, layer_thickness: float, path: List[List[Union[float, int]]], extruder_offsets: List[float]) -> bool:
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

    def processPolyline(self, line: str, path: List[List[Union[float, int]]], gcode_list: List[str]) -> bool:
        # Convering line to point array
        values_line = self._getValue(line, "$$POLYLINE")
        if not values_line:
            return (self._position, None)
        values = values_line.split(",")
        if len(values[3:]) % 2 != 0:
            return (self._position, None)
        idx = 2
        points = values[3:]
        if len(points) < 2:
            return (self._position, None)
        # TODO: add combing to this polyline
        new_position, new_gcode_position = self._cliPointToPosition(
            CliPoint(float(points[0]), float(points[1])), self._position, False)
        feedrate = self._travel_speed
        x, y, z, a, b, c, f, e = new_position
        is_retraction = self._enable_retraction and self._positionLength(
            self._position, new_position) > self._retraction_min_travel
        if is_retraction:
            #we have retraction move
            new_extruder_position = self._position.e[self._extruder_number] - self._retraction_amount
            gcode_list.append("G1 E%.5f F%.0f\n" % (new_extruder_position, (self._retraction_speed * 60)))
            self._position.e[self._extruder_number] = new_extruder_position
            self._gcode_position.e[self._extruder_number] = new_extruder_position
            path.append([self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
                         self._position.c, self._retraction_speed, self._position.e, LayerPolygon.MoveRetractionType])
        
        self._position = Position(x, y, z, a, b, c, feedrate, self._position.e)
        gcode_command = self._generateGCodeCommand(0, new_gcode_position, feedrate)
        if gcode_command is not None:
            gcode_list.append(gcode_command)
        gx, gy, gz, ga, gb, gc, gf, ge = new_gcode_position
        self._gcode_position = Position(gx, gy, gz, ga, gb, gc, feedrate, ge)
        
        path.append([x, y, z, a, b, c, feedrate, e,
                     LayerPolygon.MoveCombingType])
        
        if is_retraction:
            #we have retraction move
            new_extruder_position = self._position.e[self._extruder_number] + self._retraction_amount
            gcode_list.append("G1 E%.5f F%.0f\n" % (new_extruder_position, (self._prime_speed * 60)))
            self._position.e[self._extruder_number] = new_extruder_position
            self._gcode_position.e[self._extruder_number] = new_extruder_position
            path.append([self._position.x, self._position.y, self._position.z, self._position.a, self._position.b,
                         self._position.c, self._prime_speed, self._position.e, LayerPolygon.MoveRetractionType])

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
                gcode_list.append(gcode_command)
            gx, gy, gz, ga, gb, gc, gf, ge = new_gcode_position
            self._gcode_position = Position(gx, gy, gz, ga, gb, gc, feedrate, ge)
            path.append([x,y,z,a,b,c, feedrate, e, self._layer_type])

    def _generateGCodeCommand(self, g: int, gcode_position: Position, feedrate: float) -> Optional[str]:
            gcode_command = "G%s" % g
            if abs(gcode_position.x - self._gcode_position.x) > 0.0001:
                gcode_command += " X%.2f" % gcode_position.x
            if abs(gcode_position.y - self._gcode_position.y) > 0.0001:
                gcode_command += " Y%.2f" % gcode_position.y
            if abs(gcode_position.z - self._gcode_position.z) > 0.0001:
                gcode_command += " Z%.2f" % gcode_position.z
            if abs(gcode_position.a - self._gcode_position.a) > 0.0001:
                gcode_command += " A%.2f" % gcode_position.a
            if abs(gcode_position.b - self._gcode_position.b) > 0.0001:
                gcode_command += " B%.2f" % gcode_position.b
            if abs(gcode_position.c - self._gcode_position.c) > 0.0001:
                gcode_command += " C%.2f" % gcode_position.c
            if abs(feedrate - self._gcode_position.f) > 0.0001:
                gcode_command += " F%.0f" % (feedrate * 60)
            if abs(gcode_position.e[self._extruder_number] - self._gcode_position.e[self._extruder_number]) > 0.0001 and g > 0:
                gcode_command += " E%.5f" % gcode_position.e[self._extruder_number]
            gcode_command += "\n"
            if gcode_command != "G%s\n" % g:
                return gcode_command
            else:
                return None
        
    def _calculateExtrusion(self, current_point: List[float], previous_point: Position) -> float:
        
        Af = (self._filament_diameter / 2) ** 2 * numpy.pi
        Al = self._line_width * self._layer_thickness
        de = numpy.sqrt((current_point[0] - previous_point[0])
                        ** 2 + (current_point[1] - previous_point[1])**2 +
                         (current_point[2] - previous_point[2])**2)
        dVe = Al * de
        return dVe / Af

    def _writeStartCode(self, gcode_list: List[str]):
        gcode_list.append("T0\n")
        init_temperature = self._global_stack.getProperty(
            "material_initial_print_temperature", "value")
        init_bed_temperature = self._global_stack.getProperty(
            "material_bed_temperature_layer_0", "value")
        gcode_list.extend(["M140 S%s\n" % init_bed_temperature,
                           "M105\n",
                           "M190 S%s\n" % init_bed_temperature,
                           "M104 S%s\n" % init_temperature,
                           "M105\n",
                           "M109 S%s\n" % init_temperature,
                           "M82 ;absolute extrusion mode\n"])
        start_gcode = self._global_stack.getProperty(
            "machine_start_gcode", "value")
        gcode_list.append(start_gcode + "\n")

    def _cliPointToPosition(self, point: CliPoint, position: Position, extrusion_move: bool = True) -> (Position, Position):
        x, y, z, i, j, k = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        if self._parsing_type == "classic":
            x = point.x
            y = point.y
            z = self._current_layer_height
            i = 0
            j = 0
            k = 1
        elif self._parsing_type == "cylindrical":
            x = self._current_layer_height * math.cos(point.y)
            y = self._current_layer_height * math.sin(point.y)
            z = point.x
            length = numpy.sqrt(x**2 + y**2)
            i = x / length if length != 0 else 0
            j = y / length if length != 0 else 0
            k = 0
        new_position = Position(x,y,z,i,j,k,0, [0])
        new_gcode_position = self._transformCoordinates(x,y,z,i,j,k, self._gcode_position)
        new_position.e[self._extruder_number] = position.e[self._extruder_number] + self._calculateExtrusion([x,y,z], position) if extrusion_move else position.e[self._extruder_number]
        new_gcode_position.e[self._extruder_number] = new_position.e[self._extruder_number]
        return new_position, new_gcode_position

    @staticmethod
    def _positionLength(start: Position, end: Position) -> float:
        return numpy.sqrt((start.x - end.x)**2 + (start.y - end.y)**2 + (start.z - end.z)**2)
