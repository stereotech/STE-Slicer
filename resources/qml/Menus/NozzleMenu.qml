// Copyright (c) 2017 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.4

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Menu
{
    id: menu
    title: "Nozzle"

    property int extruderIndex: 0

    SteSlicer.NozzleModel
    {
        id: nozzleModel
    }

    Instantiator
    {
        model: nozzleModel

        MenuItem
        {
            text: model.hotend_name
            checkable: true
            checked: {
                return SteSlicer.MachineManager.activeVariantNames[extruderIndex] == model.hotend_name
            }
            exclusiveGroup: group
            onTriggered: {
                SteSlicer.MachineManager.setVariant(menu.extruderIndex, model.container_node);
            }
        }

        onObjectAdded: menu.insertItem(index, object);
        onObjectRemoved: menu.removeItem(object);
    }

    ExclusiveGroup { id: group }
}
