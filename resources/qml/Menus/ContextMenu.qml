

import QtQuick 2.2
import QtQuick.Controls 1.1
import QtQuick.Dialogs 1.2
import QtQuick.Window 2.1

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Menu
{
    id: base

    property bool shouldShowExtruders: machineExtruderCount.properties.value > 1;

    property var multiBuildPlateModel: SteSlicerApplication.getMultiBuildPlateModel()

    // Selection-related actions.
    MenuItem { action: SteSlicer.Actions.centerSelection; }
    MenuItem { action: SteSlicer.Actions.deleteSelection; }
    MenuItem { action: SteSlicer.Actions.multiplySelection; }

    // Extruder selection - only visible if there is more than 1 extruder
    MenuSeparator { visible: base.shouldShowExtruders }
    MenuItem { id: extruderHeader; text: catalog.i18ncp("@label", "Print Selected Model With:", "Print Selected Models With:", UM.Selection.selectionCount); enabled: false; visible: base.shouldShowExtruders }
    Instantiator
    {
        model: SteSlicer.ExtrudersModel { id: extrudersModel }
        MenuItem {
            text: "%1: %2 - %3".arg(model.name).arg(model.material).arg(model.variant)
            visible: base.shouldShowExtruders
            enabled: UM.Selection.hasSelection && model.enabled
            checkable: true
            checked: SteSlicer.ExtruderManager.selectedObjectExtruders.indexOf(model.id) != -1
            onTriggered: SteSlicerActions.setExtruderForSelection(model.id)
            shortcut: "Ctrl+" + (model.index + 1)
        }
        onObjectAdded: base.insertItem(index, object)
        onObjectRemoved: base.removeItem(object)
    }

    MenuSeparator {
        visible: UM.Preferences.getValue("steslicer/use_multi_build_plate")
    }

    Instantiator
    {
        model: base.multiBuildPlateModel
        MenuItem {
            enabled: UM.Selection.hasSelection
            text: base.multiBuildPlateModel.getItem(index).name;
            onTriggered: SteSlicerActions.setBuildPlateForSelection(base.multiBuildPlateModel.getItem(index).buildPlateNumber);
            checkable: true
            checked: base.multiBuildPlateModel.selectionBuildPlates.indexOf(base.multiBuildPlateModel.getItem(index).buildPlateNumber) != -1;
            visible: UM.Preferences.getValue("steslicer/use_multi_build_plate")
        }
        onObjectAdded: base.insertItem(index, object);
        onObjectRemoved: base.removeItem(object);
    }

    MenuItem {
        enabled: UM.Selection.hasSelection
        text: "New build plate";
        onTriggered: {
            SteSlicerActions.setBuildPlateForSelection(base.multiBuildPlateModel.maxBuildPlate + 1);
            checked = false;
        }
        checkable: true
        checked: false
        visible: UM.Preferences.getValue("steslicer/use_multi_build_plate")
    }

    // Global actions
    MenuSeparator {}
    MenuItem { action: SteSlicer.Actions.selectAll; }
    MenuItem { action: SteSlicer.Actions.arrangeAll; }
    MenuItem { action: SteSlicer.Actions.deleteAll; }
    MenuItem { action: SteSlicer.Actions.reloadAll; }
    MenuItem { action: SteSlicer.Actions.resetAllTranslation; }
    MenuItem { action: SteSlicer.Actions.resetAll; }

    // Group actions
    MenuSeparator {}
    MenuItem { action: SteSlicer.Actions.groupObjects; }
    MenuItem { action: SteSlicer.Actions.mergeObjects; }
    MenuItem { action: SteSlicer.Actions.unGroupObjects; }

    Connections
    {
        target: UM.Controller
        onContextMenuRequested: base.popup();
    }

    Connections
    {
        target: SteSlicer.Actions.multiplySelection
        onTriggered: multiplyDialog.open()
    }

    UM.SettingPropertyProvider
    {
        id: machineExtruderCount

        containerStack: SteSlicer.MachineManager.activeMachine
        key: "machine_extruder_count"
        watchedProperties: [ "value" ]
    }

    Dialog
    {
        id: multiplyDialog
        modality: Qt.ApplicationModal

        title: catalog.i18ncp("@title:window", "Multiply Selected Model", "Multiply Selected Models", UM.Selection.selectionCount)


        onAccepted: SteSlicerActions.multiplySelection(copiesField.value)

        signal reset()
        onReset:
        {
            copiesField.value = 1;
            copiesField.focus = true;
        }

        onVisibleChanged:
        {
            copiesField.forceActiveFocus();
        }

        standardButtons: StandardButton.Ok | StandardButton.Cancel

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width

            Label
            {
                text: catalog.i18nc("@label", "Number of Copies")
                anchors.verticalCenter: copiesField.verticalCenter
            }

            SpinBox
            {
                id: copiesField
                focus: true
                minimumValue: 1
                maximumValue: 99
            }
        }
    }

    // Find the index of an item in the list of child items of this menu.
    //
    // This is primarily intended as a helper function so we do not have to
    // hard-code the position of the extruder selection actions.
    //
    // \param item The item to find the index of.
    //
    // \return The index of the item or -1 if it was not found.
    function findItemIndex(item)
    {
        for(var i in base.items)
        {
            if(base.items[i] == item)
            {
                return i;
            }
        }
        return -1;
    }

    UM.I18nCatalog { id: catalog; name: "steslicer" }
}
