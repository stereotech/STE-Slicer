// Copyright (c) 2018 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.4

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Menu
{
    id: menu
    title: "Build plate"

    property var buildPlateModel: SteSlicerApplication.getBuildPlateModel()

    Instantiator
    {
        model: menu.buildPlateModel

        MenuItem {
            text: model.name
            checkable: true
            checked: model.name == SteSlicer.MachineManager.globalVariantName
            exclusiveGroup: group
            onTriggered: {
                SteSlicer.MachineManager.setGlobalVariant(model.container_node);
            }
        }

        onObjectAdded: menu.insertItem(index, object)
        onObjectRemoved: menu.removeItem(object)
    }

    ExclusiveGroup { id: group }
}
