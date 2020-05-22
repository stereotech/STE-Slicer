from . import GlicerConfigWriter

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")


def getMetaData():
    return {
        "mesh_writer": {
            "output": [
                {
                    "mime_type": "application/x.atss-config",
                    "mode": GlicerConfigWriter.GlicerConfigWriter.OutputMode.TextMode,
                    "extension": "atsscfg",
                    "description": i18n_catalog.i18nc("@item:inlistbox", "Config File for Glicer")
                }
            ]
        }
    }


def register(app):
    return {"mesh_writer": GlicerConfigWriter.GlicerConfigWriter()}
