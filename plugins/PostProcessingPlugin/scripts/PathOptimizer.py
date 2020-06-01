# Copyright (c) 2015 Jaime van Kessel, Ultimaker B.V.
# The PostProcessingPlugin is released under the terms of the AGPLv3 or higher.
from typing import List

from ..Script import Script

class PathOptimizer(Script):
    def __init__(self):
        super().__init__()

    def getSettingDataString(self):
        return """{
            "name":"Path optimizer script",
            "key": "PathOptimizer",
            "metadata": {},
            "version": 2,
            "settings":
            {
            }
        }"""

    def execute(self, data: List[str]) -> List[str]:
        for layer_idx, layer in enumerate(data):
            gcode = layer.split("\n")
            scanned_line_idx = 0
            movement_axis = "X"
            lines_to_remove = []
            for line_idx, line in enumerate(gcode):
                if line.startswith("G0") or line.startswith("G1"):
                    line_parts = line.split(" ")
                    if (line_parts[0] == "G0" and len(line_parts) == 2) or (line_parts[0] == "G1" and len(line_parts) == 3):
                        new_movement_axis = line_parts[1][0]
                        if new_movement_axis in ["X", "Y", "Z", "A", "B", "C"] and new_movement_axis == movement_axis:
                            if line_idx == scanned_line_idx + 1:
                                lines_to_remove.append(scanned_line_idx)
                            scanned_line_idx = line_idx
                        movement_axis = new_movement_axis
            if len(lines_to_remove) > 0:
                for line_to_remove in lines_to_remove:
                    gcode[line_to_remove] = ""
                gcode = list(filter(lambda line: line != "", gcode))
                data[layer_idx] = "\n".join(gcode) + "\n"
        return data