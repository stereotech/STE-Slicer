// Copyright (c) 2016 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Window 2.1

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer


UM.ManagementPage
{
    id: base;

    title: catalog.i18nc("@title:tab", "Printers");
    model: SteSlicer.MachineManagementModel { }

    activeId: SteSlicer.MachineManager.activeMachineId
    activeIndex: activeMachineIndex()

    function activeMachineIndex()
    {
        for(var i = 0; i < model.rowCount(); i++) {
            if (model.getItem(i).id == SteSlicer.MachineManager.activeMachineId) {
                return i;
            }
        }
        return -1;
    }

    buttons: [
        Button
        {
            text: catalog.i18nc("@action:button", "Activate");
            iconName: "list-activate";
            enabled: base.currentItem != null && base.currentItem.id != SteSlicer.MachineManager.activeMaterialId
            onClicked: SteSlicer.MachineManager.setActiveMachine(base.currentItem.id)
        },
        Button
        {
            text: catalog.i18nc("@action:button", "Add");
            iconName: "list-add";
            onClicked: SteSlicerApplication.requestAddPrinter()
        },
        Button
        {
            text: catalog.i18nc("@action:button", "Remove");
            iconName: "list-remove";
            enabled: base.currentItem != null && model.rowCount() > 1
            onClicked: confirmDialog.open();
        },
        Button
        {
            text: catalog.i18nc("@action:button", "Rename");
            iconName: "edit-rename";
            enabled: base.currentItem != null && base.currentItem.metadata.connect_group_name == null
            onClicked: renameDialog.open();
        }
    ]

    Item
    {
        visible: base.currentItem != null
        anchors.fill: parent

        Label
        {
            id: machineName
            text: base.currentItem && base.currentItem.name ? base.currentItem.name : ""
            font: UM.Theme.getFont("large")
            width: parent.width
            elide: Text.ElideRight
        }

        Flow
        {
            id: machineActions
            visible: currentItem && currentItem.id == SteSlicer.MachineManager.activeMachineId
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: machineName.bottom
            anchors.topMargin: UM.Theme.getSize("default_margin").height

            Repeater
            {
                id: machineActionRepeater
                model: base.currentItem ? SteSlicer.MachineActionManager.getSupportedActions(SteSlicer.MachineManager.getDefinitionByMachineId(base.currentItem.id)) : null

                Item
                {
                    width: childrenRect.width + 2 * screenScaleFactor
                    height: childrenRect.height
                    Button
                    {
                        text: machineActionRepeater.model[index].label
                        onClicked:
                        {
                            actionDialog.content = machineActionRepeater.model[index].displayItem;
                            machineActionRepeater.model[index].displayItem.reset();
                            actionDialog.title = machineActionRepeater.model[index].label;
                            actionDialog.show();
                        }
                    }
                }
            }
        }

        UM.Dialog
        {
            id: actionDialog
            property var content
            onContentChanged:
            {
                contents = content;
                content.onCompleted.connect(hide)
                content.dialog = actionDialog
            }
            rightButtons: Button
            {
                text: catalog.i18nc("@action:button", "Close")
                iconName: "dialog-close"
                onClicked: actionDialog.reject()
            }
        }

        Grid
        {
            id: machineInfo

            anchors.top: machineActions.visible ? machineActions.bottom : machineActions.anchors.top
            anchors.topMargin: UM.Theme.getSize("default_margin").height
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: UM.Theme.getSize("default_margin").height
            rowSpacing: UM.Theme.getSize("default_lining").height
            columns: 2

            visible: base.currentItem

            property bool printerConnected: SteSlicer.MachineManager.printerConnected
            property var connectedPrinter: printerConnected ? SteSlicer.MachineManager.printerOutputDevices[0] : null
            property bool printerAcceptsCommands: printerConnected && SteSlicer.MachineManager.printerOutputDevices[0].acceptsCommands
            property var printJob: connectedPrinter != null ? connectedPrinter.activePrintJob: null
            Label
            {
                text: catalog.i18nc("@label", "Printer type:")
                visible: base.currentItem && "definition_name" in base.currentItem.metadata
            }
            Label
            {
                text: (base.currentItem && "definition_name" in base.currentItem.metadata) ? base.currentItem.metadata.definition_name : ""
            }
            Label
            {
                text: catalog.i18nc("@label", "Connection:")
                visible: base.currentItem && base.currentItem.id == SteSlicer.MachineManager.activeMachineId
            }
            Label
            {
                width: (parent.width * 0.7) | 0
                text: machineInfo.printerConnected ? machineInfo.connectedPrinter.connectionText : catalog.i18nc("@info:status", "The printer is not connected.")
                visible: base.currentItem && base.currentItem.id == SteSlicer.MachineManager.activeMachineId
                wrapMode: Text.WordWrap
            }
            Label
            {
                text: catalog.i18nc("@label", "State:")
                visible: base.currentItem && base.currentItem.id == SteSlicer.MachineManager.activeMachineId && machineInfo.printerAcceptsCommands
            }
            Label {
                width: (parent.width * 0.7) | 0
                text:
                {
                    if(!machineInfo.printerConnected || !machineInfo.printerAcceptsCommands) {
                        return "";
                    }

                    if (machineInfo.printJob == null)
                    {
                        return catalog.i18nc("@label:MonitorStatus", "Waiting for a printjob");
                    }

                    switch(machineInfo.printJob.state)
                    {
                        case "printing":
                            return catalog.i18nc("@label:MonitorStatus", "Printing...");
                        case "paused":
                            return catalog.i18nc("@label:MonitorStatus", "Paused");
                        case "pre_print":
                            return catalog.i18nc("@label:MonitorStatus", "Preparing...");
                        case "wait_cleanup":
                            return catalog.i18nc("@label:MonitorStatus", "Waiting for someone to clear the build plate");
                        case "error":
                            return printerOutputDevice.errorText;
                        case "maintenance":
                            return catalog.i18nc("@label:MonitorStatus", "In maintenance. Please check the printer");
                        case "abort":  // note sure if this jobState actually occurs in the wild
                            return catalog.i18nc("@label:MonitorStatus", "Aborting print...");

                    }
                    return ""
                }
                visible: base.currentItem && base.currentItem.id == SteSlicer.MachineManager.activeMachineId && machineInfo.printerAcceptsCommands
                wrapMode: Text.WordWrap
            }
        }

        Column {
            id: additionalComponentsColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: machineInfo.visible ? machineInfo.bottom : machineInfo.anchors.top
            anchors.topMargin: UM.Theme.getSize("default_margin").width

            spacing: UM.Theme.getSize("default_margin").width
            visible: base.currentItem && base.currentItem.id == SteSlicer.MachineManager.activeMachineId

            Component.onCompleted:
            {
                for (var component in SteSlicerApplication.additionalComponents["machinesDetailPane"]) {
                    SteSlicerApplication.additionalComponents["machinesDetailPane"][component].parent = additionalComponentsColumn
                }
            }
        }

        Component.onCompleted: {
            addAdditionalComponents("machinesDetailPane")
        }

        Connections {
            target: SteSlicerApplication
            onAdditionalComponentsChanged: addAdditionalComponents
        }

        function addAdditionalComponents (areaId) {
            if(areaId == "machinesDetailPane") {
                for (var component in SteSlicerApplication.additionalComponents["machinesDetailPane"]) {
                    SteSlicerApplication.additionalComponents["machinesDetailPane"][component].parent = additionalComponentsColumn
                }
            }
        }

        UM.I18nCatalog { id: catalog; name: "steslicer"; }

        UM.ConfirmRemoveDialog
        {
            id: confirmDialog;
            object: base.currentItem && base.currentItem.name ? base.currentItem.name : "";
            onYes:
            {
                SteSlicer.MachineManager.removeMachine(base.currentItem.id);
                if(!base.currentItem)
                {
                    objectList.currentIndex = activeMachineIndex()
                }
                //Force updating currentItem and the details panel
                objectList.onCurrentIndexChanged()
            }
        }

        UM.RenameDialog
        {
            id: renameDialog;
            width: 300 * screenScaleFactor
            height: 150 * screenScaleFactor
            object: base.currentItem && base.currentItem.name ? base.currentItem.name : "";
            property var machine_name_validator: SteSlicer.MachineNameValidator { }
            validName: renameDialog.newName.match(renameDialog.machine_name_validator.machineNameRegex) != null;
            onAccepted:
            {
                SteSlicer.MachineManager.renameMachine(base.currentItem.id, newName.trim());
                //Force updating currentItem and the details panel
                objectList.onCurrentIndexChanged()
            }
        }

        Connections
        {
            target: SteSlicer.MachineManager
            onGlobalContainerChanged:
            {
                objectList.currentIndex = activeMachineIndex()
                objectList.onCurrentIndexChanged()
            }
        }

    }
}
