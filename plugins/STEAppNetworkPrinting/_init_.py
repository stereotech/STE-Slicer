from .src import DiscoverSTEAppAction
from .src import STEAppOutputDevicePlugin

def getMetaData():
    return {}

def register(app):
    return { "output_device": STEAppOutputDevicePlugin.STEAppOutputDevicePlugin(), "machine_action": DiscoverSTEAppAction.DiscoverSTEAppAction()}