

from . import SolidView

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "view": {
            "name": i18n_catalog.i18nc("@item:inmenu", "Solid view"),
            "weight": 0
        }
    }

def register(app):
    return { "view": SolidView.SolidView() }
