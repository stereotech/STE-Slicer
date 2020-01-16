

from .src import DiscoverUM3Action
from .src import UM3OutputDevicePlugin

def getMetaData():
    return {}

def register(app):
    return { "output_device": UM3OutputDevicePlugin.UM3OutputDevicePlugin(), "machine_action": DiscoverUM3Action.DiscoverUM3Action()}