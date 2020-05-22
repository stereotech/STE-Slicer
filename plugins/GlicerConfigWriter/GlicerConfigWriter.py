from math import radians
from typing import Dict, List, NamedTuple, Optional, Union
import re
import math
import numpy
import xml.etree.ElementTree as eltree

from UM.Mesh.MeshWriter import MeshWriter

from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode

from UM.Logger import Logger
from UM.Job import Job
from UM.Message import Message
from UM.i18n import i18nCatalog
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


class GlicerConfigWriter(MeshWriter):
    def write(self, stream, nodes, mode=MeshWriter.OutputMode.TextMode):
        xml_config = self.generate()
        stream.write(xml_config)
        return True

    def __init__(self):
        super().__init__()


    def generate(self):
        application = SteSlicerApplication.getInstance()
        extruder_stack = application.getExtruderManager().getActiveExtruderStack()
        root = eltree.Element("root")
        for region, params in params_dict.items():
            for name, value in params.items():
                sub = eltree.SubElement(root, "param", attrib={'NAME': name, 'REGION': region, 'PARAM': ''})
                setting_value = extruder_stack.getProperty(value.get("stack_key", ""), "value")
                if setting_value is not None:
                    if isinstance(setting_value, bool):
                        if setting_value:
                            setting_value = "1"
                        else:
                            setting_value = "0"
                    if name in ["rsize", "first_offset", "last_offset"]:
                        setting_value /= 2
                    if name == "skin_width":
                        setting_value = setting_value if setting_value <= 4 else 4
                else:
                    setting_value = value.get("default_value", "")
                sub.text = setting_value.__str__()
        return eltree.tostring(root, encoding='Windows-1251').decode("Windows-1251")
