// Copyright (c) 2018 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.4

import UM 1.2 as UM
import Cura 1.0 as Cura

Menu
{
    id: menu

    Instantiator
    {
        model: Cura.QualityProfilesDropDownMenuModel

        MenuItem
        {
            text: (model.layer_height != "") ? model.name + " - " + model.layer_height + model.layer_height_unit : model.name
            checkable: true
            checked: Cura.MachineManager.activeQualityOrQualityChangesName == model.name
            exclusiveGroup: group
            onTriggered: {
                Cura.MachineManager.setQualityGroup(model.quality_group)
            }
            visible: model.available
        }

        onObjectAdded: menu.insertItem(index, object);
        onObjectRemoved: menu.removeItem(object);
    }

    MenuSeparator
    {
        id: customSeparator
        visible: Cura.CustomQualityProfilesDropDownMenuModel.rowCount > 0
    }

    Instantiator
    {
        id: customProfileInstantiator
        model: Cura.CustomQualityProfilesDropDownMenuModel

        Connections
        {
            target: Cura.CustomQualityProfilesDropDownMenuModel
            onModelReset: customSeparator.visible = Cura.CustomQualityProfilesDropDownMenuModel.rowCount() > 0
        }

        MenuItem
        {
            text: model.name
            checkable: true
            checked: Cura.MachineManager.activeQualityOrQualityChangesName == model.name
            exclusiveGroup: group
            onTriggered: Cura.MachineManager.setQualityChangesGroup(model.quality_changes_group)
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

    MenuItem { action: Cura.Actions.addProfile }
    MenuItem { action: Cura.Actions.updateProfile }
    MenuItem { action: Cura.Actions.resetProfile }
    MenuSeparator { }
    MenuItem { action: Cura.Actions.manageProfiles }
}
