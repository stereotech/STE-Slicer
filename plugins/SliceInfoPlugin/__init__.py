

from . import SliceInfo


def getMetaData():
    return {}

def register(app):
    return { "extension": SliceInfo.SliceInfo()}