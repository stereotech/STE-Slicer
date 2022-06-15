from ..Script import Script

from UM.Application import Application #To get the current printer's settings.

class SetPauseScript(Script):
    def __init__(self):
        super().__init__()

    def getSettingDataString(self):
        return """{
               "name": "Set Pause",
               "key": "SetPauseScript",
               "metadata": {},
               "version": 2,
               "settings":
               {
                   "pause_at":
                   {
                       "label": "Pause At",
                       "description": "Whether to pause at a certain height or at a certain layer.",
                       "type": "enum",
                       "options": {"layer_no": "Layer No."},
                       "default_value": "layer_no"
                   },
                   "pause_layer":
                   {
                       "label": "Pause Layer",
                       "description": "At what layer should the pause occur?",
                       "type": "int",
                       "value": 5,
                       "minimum_value": "0",
                       "minimum_value_warning": "1",
                       "enabled": "pause_at == 'layer_no'"
                   },
                   "z_offset":
                   {
                       "label": "Z offset",
                       "description": "z-axis offset",
                       "type": "float",
                       "value": 0.0,
                       "minimum_value": "0",
                       "minimum_value_warning": "0",
                       "maximum_value": "0.4",
                       "maximum_value_warning": "0.3",
                       "enabled": "pause_at == 'layer_no'"
                   }
               }
           }"""

    def execute(self, data: list):
        """data is a list. Each index contains a layer"""
        pause_layer = self.getSettingValueByKey("pause_layer")
        z_offset = self.getSettingValueByKey("z_offset")

        intermediate_data = data
        for index, layer in enumerate(data):
            res = [i for i in range(len(layer)) if layer.startswith(";LAYER:", i)]
            if len(res) > 1:
                my_list = layer.rsplit(';LAYER:', len(res)-1)
                for i in range(len(res)):
                    if my_list[i].startswith(";LAYER:"):
                        intermediate_data[index] = my_list[i]
                        continue
                    my_list[i] = ";LAYER:" + my_list[i]
                    intermediate_data.insert(index+i, my_list[i])

        layer_index = [idx for idx, layer in enumerate(intermediate_data) if ";LAYER:" in layer]
        prepend_gcode = ";TYPE:CUSTOM\n"
        prepend_gcode += ";added code by post processing\n"
        prepend_gcode += ";script: SetPauseScript.py\n"
        prepend_gcode += ";current layer: {layer}\n".format(layer=pause_layer)
        prepend_gcode += "PAUSE\n"
        if z_offset > 0.0:
            prepend_gcode += "SET_GCODE_OFFSET Z_ADJUST=-{amount} MOVE=1\n".format(amount=z_offset)

        # Override the data of this layer with the
        # modified data
        intermediate_data[layer_index[pause_layer]] += prepend_gcode
        return intermediate_data
