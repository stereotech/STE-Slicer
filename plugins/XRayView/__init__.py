

from . import XRayView

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "view": {
            "name": catalog.i18nc("@item:inlistbox", "X-Ray view"),
            "weight": 1
        }
    }

def register(app):
    return { "view": XRayView.XRayView() }
