from . import LayersProcessorBackend

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "backend_engine": {
            "types": [
                "spherical"
            ]
        }
    }

def register(app):
    return { "backend": LayersProcessorBackend.LayersProcessorBackend() }