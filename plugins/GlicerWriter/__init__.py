from . import GlicerWriter

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")


def getMetaData():
    return {
        "mesh_writer": {
            "output": [
                {
                    "mime_type": "model/x.stl-binary",
                    "mode": 2,
                    "extension": "stl",
                    "description": i18n_catalog.i18nc("@item:inlistbox", "STL File for Glicer")
                }
            ]
        }
    }


def register(app):
    return {"mesh_writer": GlicerWriter.GlicerWriter()}
