

from . import FirmwareUpdateChecker


def getMetaData():
    return {}


def register(app):
    return {"extension": FirmwareUpdateChecker.FirmwareUpdateChecker()}
