

from . import MachineSettingsAction


def getMetaData():
    return {}

def register(app):
    return { "machine_action": MachineSettingsAction.MachineSettingsAction() }
