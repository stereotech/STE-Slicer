

from . import ModelChecker


def getMetaData():
    return {}

def register(app):
    return { "extension": ModelChecker.ModelChecker() }
