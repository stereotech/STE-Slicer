

from . import ChangeLog


def getMetaData():
    return {}

def register(app):
    return {"extension": ChangeLog.ChangeLog()}
