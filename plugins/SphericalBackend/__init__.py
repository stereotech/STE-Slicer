from . import SphericalBackend

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "backend_engine": {
            "type": "spherical_full"
        }
    }

def register(app):
    return { "backend": SphericalBackend.SphericalBackend() }