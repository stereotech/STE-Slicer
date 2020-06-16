from . import CliParserBackend

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "backend_engine": {
            "types": [
                "cylindrical",
                "spherical"
            ]
        }
    }

def register(app):
    return { "backend": CliParserBackend.CliParserBackend() }