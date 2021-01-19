from . import DescreteSlicerBackend

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "backend_engine": {
            "types": [
                "discrete"
            ]
        }
    }

def register(app):
    return { "backend": DescreteSlicerBackend.DescreteSlicerBackend() }