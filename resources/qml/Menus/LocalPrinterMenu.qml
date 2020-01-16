

import QtQuick 2.2
import QtQuick.Controls 1.4

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Instantiator {
    model: UM.ContainerStacksModel {
        filter: {"type": "machine", "um_network_key": null}
    }
    MenuItem {
        text: model.name;
        checkable: true;
        checked: SteSlicer.MachineManager.activeMachineId == model.id
        exclusiveGroup: group;
        onTriggered: SteSlicer.MachineManager.setActiveMachine(model.id);
    }
    onObjectAdded: menu.insertItem(index, object)
    onObjectRemoved: menu.removeItem(object)
}
