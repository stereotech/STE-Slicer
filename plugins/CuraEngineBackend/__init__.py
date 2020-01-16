

#Shoopdawoop
from . import CuraEngineBackend

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {}

def register(app):
    return { "backend": CuraEngineBackend.CuraEngineBackend() }

