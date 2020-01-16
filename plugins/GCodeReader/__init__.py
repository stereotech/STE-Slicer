
from . import GCodeReader

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "mesh_reader": [
            {
                "extension": "gcode",
                "description": i18n_catalog.i18nc("@item:inlistbox", "G-code File")
            },
            {
                "extension": "g",
                "description": i18n_catalog.i18nc("@item:inlistbox", "G File")
            }
        ]
    }


def register(app):
    app.addNonSliceableExtension(".gcode")
    app.addNonSliceableExtension(".g")
    return {"mesh_reader": GCodeReader.GCodeReader()}
