

from . import GCodeWriter

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {


        "mesh_writer": {
            "output": [{
                "extension": "gcode",
                "description": catalog.i18nc("@item:inlistbox", "G-code File"),
                "mime_type": "text/x-gcode",
                "mode": GCodeWriter.GCodeWriter.OutputMode.TextMode
            }]
        }
    }

def register(app):
    return { "mesh_writer": GCodeWriter.GCodeWriter() }
