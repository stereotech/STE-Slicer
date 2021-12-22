from . import PlaneSplitter

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "tool": {
            "name": i18n_catalog.i18nc("@label", "Plane Splitter"),
            "description": i18n_catalog.i18nc("@info:tooltip", "Create planes for 5D Discrete"),
            "icon": "layers-plus.svg",
            "weight": 5
        }
    }

def register(app):
    return { "tool": PlaneSplitter.PlaneSplitter() }