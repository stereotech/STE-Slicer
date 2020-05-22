from . import GlicerBackend

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "backend_engine": {
            "type": "cylindrical"
        }
    }

def register(app):
    return { "backend": GlicerBackend.GlicerBackend() }