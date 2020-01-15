// Copyright (c) 2018 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.4

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Menu
{
    id: menu

    Instantiator
    {
        model: SteSlicer.QualityProfilesDropDownMenuModel

        MenuItem
        {
            text: (model.layer_height != "") ? model.name + " - " + model.layer_height + model.layer_height_unit : model.name
            checkable: true
            checked: SteSlicer.MachineManager.activeQualityOrQualityChangesName == model.name
            exclusiveGroup: group
            onTriggered: {
                SteSlicer.MachineManager.setQualityGroup(model.quality_group)
            }
            visible: model.available
        }

        onObjectAdded: menu.insertItem(index, object);
        onObjectRemoved: menu.removeItem(object);
    }

    MenuSeparator
    {
        id: customSeparator
        visible: SteSlicer.CustomQualityProfilesDropDownMenuModel.rowCount > 0
    }

    Instantiator
    {
        id: customProfileInstantiator
        model: SteSlicer.CustomQualityProfilesDropDownMenuModel

        Connections
        {
            target: SteSlicer.CustomQualityProfilesDropDownMenuModel
            onModelReset: customSeparator.visible = SteSlicer.CustomQualityProfilesDropDownMenuModel.rowCount() > 0
        }

        MenuItem
        {
            text: model.name
            checkable: true
            checked: SteSlicer.MachineManager.activeQualityOrQualityChangesName == model.name
            exclusiveGroup: group
            onTriggered: SteSlicer.MachineManager.setQualityChangesGroup(model.quality_changes_group)
        }

        onObjectAdded:
        {
            customSeparator.visible = model.rowCount() > 0;
            menu.insertItem(index, object);
        }
        onObjectRemoved:
        {
            customSeparator.visible = model.rowCount() > 0;
            menu.removeItem(object);
        }
    }

    ExclusiveGroup { id: group; }

    MenuSeparator { id: profileMenuSeparator }

    MenuItem { action: SteSlicer.Actions.addProfile }
    MenuItem { action: SteSlicer.Actions.updateProfile }
    MenuItem { action: SteSlicer.Actions.resetProfile }
    MenuSeparator { }
    MenuItem { action: SteSlicer.Actions.manageProfiles }
}
