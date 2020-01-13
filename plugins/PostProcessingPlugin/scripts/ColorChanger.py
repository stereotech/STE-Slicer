from typing import List

from ..Script import Script

class ColorChanger(Script):
    def __init__(self):
        super().__init__()
        self._r = 255
        self._g = 0
        self._b = 0

    def getSettingDataString(self):
        return """{
            "name":"Color Changer",
            "key": "ColorChanger",
            "metadata": {},
            "version": 2,
            "settings":
            {
                "change_type":
                {
                    "label": "Change Type",
                    "description": "Type of the animation",
                    "type": "enum",
                    "options": {
                        "fade": "Fade", 
                        "flash": "Flash"
                    },
                    "default_value": "fade"
                },
                "speed":
                {
                    "label": "Speed",
                    "description": "Animation Speed",
                    "type": "int",
                    "default_value": 50,
                    "minimum_value": "1",
                    "minimum_value_warning": "1",
                    "maximum_value_warning": "100"
                }
            }
        }"""

    def execute(self, data: List[str]) -> List[str]:
        index = 0
        step = self.getSettingValueByKey("speed")
        layer_start_idx = 0
        for layer_number, layer in enumerate(data):
            layer_lines = data[layer_number].splitlines(keepends=True)
            idx = layer_start_idx
            while idx < len(layer_lines):
                layer_lines.insert(idx, ";COLOR CHANGE HERE\n")
                idx += step
            layer_start_idx = len(layer_lines) % step
            data[layer_number] = str.join(layer_lines)
            index += len(layer_lines)

        return data
