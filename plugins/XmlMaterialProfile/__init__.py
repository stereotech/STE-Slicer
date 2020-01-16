

from . import XmlMaterialProfile
from . import XmlMaterialUpgrader

from UM.MimeTypeDatabase import MimeType, MimeTypeDatabase

upgrader = XmlMaterialUpgrader.XmlMaterialUpgrader()


def getMetaData():
    return {
        "settings_container": {
            "type": "material",
            "mimetype": "application/x-ultimaker-material-profile"
        },
        "version_upgrade": {
            ("materials", 1000000): ("materials", 1000004, upgrader.upgradeMaterial),
        },
        "sources": {
            "materials": {
                "get_version": upgrader.getXmlVersion,
                "location": {"./materials"}
            },
        }
    }


def register(app):
    # add Mime type
    mime_type = MimeType(
        name = "application/x-ultimaker-material-profile",
        comment = "Ultimaker Material Profile",
        suffixes = [ "xml.fdm_material" ]
    )
    MimeTypeDatabase.addMimeType(mime_type)

    # add upgrade version
    from steslicer.SteSlicerApplication import SteSlicerApplication
    from UM.VersionUpgradeManager import VersionUpgradeManager
    VersionUpgradeManager.getInstance().registerCurrentVersion(
        ("materials", XmlMaterialProfile.XmlMaterialProfile.Version * 1000000 + SteSlicerApplication.SettingVersion),
        (SteSlicerApplication.ResourceTypes.MaterialInstanceContainer, "application/x-ultimaker-material-profile")
    )

    return {"version_upgrade": upgrader,
            "settings_container": XmlMaterialProfile.XmlMaterialProfile("default_xml_material_profile"),
            }
