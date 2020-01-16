

import QtQuick 2.7
import QtQuick.Controls 1.4

import UM 1.3 as UM
import SteSlicer 1.0 as SteSlicer

Menu
{
    id: menu
    title: "Printer type"
    property var outputDevice: SteSlicer.MachineManager.printerOutputDevices[0]

    Instantiator
    {
        id: printerTypeInstantiator
        model: outputDevice != null ? outputDevice.connectedPrintersTypeCount : []

        MenuItem
        {
            text: modelData.machine_type
            checkable: true
            checked: SteSlicer.MachineManager.activeMachineDefinitionName == modelData.machine_type
            exclusiveGroup: group
            onTriggered:
            {
                SteSlicer.MachineManager.switchPrinterType(modelData.machine_type)
            }
        }
        onObjectAdded: menu.insertItem(index, object)
        onObjectRemoved: menu.removeItem(object)
    }

    ExclusiveGroup { id: group }
}
