from . import CylindricalBackend

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "backend_engine": {
            "type": "cylindrical_full"
        }
    }

def register(app):
    return { "backend": CylindricalBackend.CylindricalBackend() }