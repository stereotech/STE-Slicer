

import QtQuick 2.7
import QtQuick.Controls 1.4

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Menu
{
    id: menu
    title: catalog.i18nc("@action:inmenu", "Visible Settings")

    property QtObject settingVisibilityPresetsModel: SteSlicerApplication.getSettingVisibilityPresetsModel()

    signal showAllSettings()

    Instantiator
    {
        model: settingVisibilityPresetsModel.items

        MenuItem
        {
            text: modelData.name
            checkable: true
            checked: modelData.presetId == settingVisibilityPresetsModel.activePreset
            exclusiveGroup: group
            onTriggered:
            {
                settingVisibilityPresetsModel.setActivePreset(modelData.presetId);
            }
        }

        onObjectAdded: menu.insertItem(index, object)
        onObjectRemoved: menu.removeItem(object)
    }

    MenuSeparator {}
    MenuItem
    {
        text: catalog.i18nc("@action:inmenu", "Show All Settings")
        checkable: false
        exclusiveGroup: group
        onTriggered:
        {
            showAllSettings();
        }
    }
    MenuSeparator {}
    MenuItem
    {
        text: catalog.i18nc("@action:inmenu", "Manage Setting Visibility...")
        iconName: "configure"
        onTriggered: SteSlicer.Actions.configureSettingVisibility.trigger()
    }

    ExclusiveGroup { id: group }
}
