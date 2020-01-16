

from . import PrepareStage

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "stage": {
            "name": i18n_catalog.i18nc("@item:inmenu", "Prepare"),
            "weight": 0
        }
    }

def register(app):
    return {
        "stage": PrepareStage.PrepareStage()
    }
