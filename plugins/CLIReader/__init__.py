
from . import CliReader
from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")


def getMetaData():
    return {
        "mesh_reader": [
            {
                "extension": "cli",
                "description": i18n_catalog.i18nc("@item:inlistbox", "CLI File")
            }
        ]
    }


def register(app):
    app.addNonSliceableExtension(".cli")
    return {"mesh_reader": CliReader.CliReader()}
