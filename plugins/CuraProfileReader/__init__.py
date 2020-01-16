

from . import CuraProfileReader

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "profile_reader": [
            {
                "extension": "steslicerprofile",
                "description": catalog.i18nc("@item:inlistbox", "STE Slicer Profile")
            }
        ]
    }

def register(app):
    return { "profile_reader": CuraProfileReader.CuraProfileReader() }
