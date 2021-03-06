

from . import SupportEraser

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("steslicer")

def getMetaData():
    return {
        "tool": {
            "name": i18n_catalog.i18nc("@label", "Support Blocker"),
            "description": i18n_catalog.i18nc("@info:tooltip", "Create a volume in which supports are not printed."),
            "icon": "tool_icon.svg",
            "weight": 4
        }
    }

def register(app):
    return { "tool": SupportEraser.SupportEraser() }
