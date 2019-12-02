// Copyright (c) 2018 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import UM 1.2 as UM
import Cura 1.0 as Cura

import QtQuick 2.2
import QtQuick.Controls 1.1
import QtQuick.Layouts 1.1
import QtQuick.Window 2.1
import QtQuick.Dialogs 1.2

Cura.MachineAction
{
    id: base
    anchors.fill: parent;
    property var selectedDevice: null
    property bool completeProperties: true

    function connectToPrinter()
    {
        if(base.selectedDevice && base.completeProperties)
        {
            var printerKey = base.selectedDevice.key
            var printerName = base.selectedDevice.name  // TODO To change when the groups have a name
            if (manager.getStoredKey() != printerKey)
            {
                // Check if there is another instance with the same key
                if (!manager.existsKey(printerKey))
                {
                    manager.setKey(printerKey)
                    manager.setGroupName(printerName)   // TODO To change when the groups have a name
                    completed()
                }
                else
                {
                    existingConnectionDialog.open()
                }
            }
        }
    }

    MessageDialog
    {
        id: existingConnectionDialog
        title: catalog.i18nc("@window:title", "Existing Connection")
        icon: StandardIcon.Information
        text: catalog.i18nc("@message:text", "This printer/group is already added to Cura. Please select another printer/group.")
        standardButtons: StandardButton.Ok
        modality: Qt.ApplicationModal
    }

    Column
    {
        anchors.fill: parent;
        id: discoverUM3Action
        spacing: UM.Theme.getSize("default_margin").height

        SystemPalette { id: palette }
        UM.I18nCatalog { id: catalog; name:"cura" }
        Label
        {
            id: pageTitle
            width: parent.width
            text: catalog.i18nc("@title:window", "Connect to Networked Printer")
            wrapMode: Text.WordWrap
            font.pointSize: 18
        }

        Label
        {
            id: pageDescription
            width: parent.width
            wrapMode: Text.WordWrap
            text: catalog.i18nc("@label", "To print directly to your printer over the network, please make sure your printer is connected to the network using a network cable or by connecting your printer to your WIFI network. If you don't connect Cura with your printer, you can still use a USB drive to transfer g-code files to your printer.\n\nSelect your printer from the list below:")
        }

        Row
        {
            spacing: UM.Theme.getSize("default_lining").width

            Button
            {
                id: addButton
                text: catalog.i18nc("@action:button", "Add");
                onClicked:
                {
                    manualPrinterDialog.showDialog("", "");
                }
            }

            Button
            {
                id: editButton
                text: catalog.i18nc("@action:button", "Edit")
                enabled: base.selectedDevice != null && base.selectedDevice.getProperty("manual") == "true"
                onClicked:
                {
                    manualPrinterDialog.showDialog(base.selectedDevice.key, base.selectedDevice.ipAddress);
                }
            }

            Button
            {
                id: removeButton
                text: catalog.i18nc("@action:button", "Remove")
                enabled: base.selectedDevice != null && base.selectedDevice.getProperty("manual") == "true"
                onClicked: manager.removeManualDevice(base.selectedDevice.key, base.selectedDevice.ipAddress)
            }

            Button
            {
                id: rediscoverButton
                text: catalog.i18nc("@action:button", "Refresh")
                onClicked: manager.restartDiscovery()
            }
        }

        Row
        {
            id: contentRow
            width: parent.width
            spacing: UM.Theme.getSize("default_margin").width

            Column
            {
                width: Math.round(parent.width * 0.5)
                spacing: UM.Theme.getSize("default_margin").height

                ScrollView
                {
                    id: objectListContainer
                    frameVisible: true
                    width: parent.width
                    height: base.height - contentRow.y - discoveryTip.height

                    Rectangle
                    {
                        parent: viewport
                        anchors.fill: parent
                        color: palette.light
                    }

                    ListView
                    {
                        id: listview
                        model: manager.foundDevices
                        onModelChanged:
                        {
                            var selectedKey = manager.getLastManualEntryKey()
                            // If there is no last manual entry key, then we select the stored key (if any)
                            if (selectedKey == "")
                                selectedKey = manager.getStoredKey()
                            for(var i = 0; i < model.length; i++) {
                                if(model[i].key == selectedKey)
                                {
                                    currentIndex = i;
                                    return
                                }
                            }
                            currentIndex = -1;
                        }
                        width: parent.width
                        currentIndex: -1
                        onCurrentIndexChanged:
                        {
                            base.selectedDevice = listview.model[currentIndex];
                            // Only allow connecting if the printer has responded to API query since the last refresh
                            base.completeProperties = base.selectedDevice != null && base.selectedDevice.getProperty("incomplete") != "true";
                        }
                        Component.onCompleted: manager.startDiscovery()
                        delegate: Rectangle
                        {
                            height: childrenRect.height
                            color: ListView.isCurrentItem ? palette.highlight : index % 2 ? palette.base : palette.alternateBase
                            width: parent.width
                            Label
                            {
                                anchors.left: parent.left
                                anchors.leftMargin: UM.Theme.getSize("default_margin").width
                                anchors.right: parent.right
                                text: listview.model[index].name
                                color: parent.ListView.isCurrentItem ? palette.highlightedText : palette.text
                                elide: Text.ElideRight
                            }

                            MouseArea
                            {
                                anchors.fill: parent;
                                onClicked:
                                {
                                    if(!parent.ListView.isCurrentItem)
                                    {
                                        parent.ListView.view.currentIndex = index;
                                    }
                                }
                            }
                        }
                    }
                }
                Label
                {
                    id: discoveryTip
                    anchors.left: parent.left
                    anchors.right: parent.right
                    wrapMode: Text.WordWrap
                    text: catalog.i18nc("@label", "If your printer is not listed, read the <a href='%1'>network printing troubleshooting guide</a>").arg("https://ultimaker.com/en/troubleshooting");
                    onLinkActivated: Qt.openUrlExternally(link)
                }

            }
            Column
            {
                width: Math.round(parent.width * 0.5)
                visible: base.selectedDevice ? true : false
                spacing: UM.Theme.getSize("default_margin").height
                Label
                {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: base.selectedDevice ? base.selectedDevice.name : ""
                    font: UM.Theme.getFont("large")
                    elide: Text.ElideRight
                }
                Grid
                {
                    visible: base.completeProperties
                    width: parent.width
                    columns: 2
                    Label
                    {
                        width: Math.round(parent.width * 0.5)
                        wrapMode: Text.WordWrap
                        text: catalog.i18nc("@label", "Type")
                    }
                    Label
                    {
                        width: Math.round(parent.width * 0.5)
                        wrapMode: Text.WordWrap
                        text:
                        {
                            if(base.selectedDevice)
                            {
                                if (base.selectedDevice.printerType == "ultimaker3")
                                {
                                    return "Ultimaker 3";
                                }
                                else if (base.selectedDevice.printerType == "ultimaker3_extended")
                                {
                                    return "Ultimaker 3 Extended";
                                }
                                else if (base.selectedDevice.printerType == "ultimaker_s5")
                                {
                                    return "Ultimaker S5";
                                }
                                else
                                {
                                    return catalog.i18nc("@label", "Unknown") // We have no idea what type it is. Should not happen 'in the field'
                                }
                            }
                            else
                            {
                                return ""
                            }
                        }
                    }
                    Label
                    {
                        width: Math.round(parent.width * 0.5)
                        wrapMode: Text.WordWrap
                        text: catalog.i18nc("@label", "Firmware version")
                    }
                    Label
                    {
                        width: Math.round(parent.width * 0.5)
                        wrapMode: Text.WordWrap
                        text: base.selectedDevice ? base.selectedDevice.firmwareVersion : ""
                    }
                    Label
                    {
                        width: Math.round(parent.width * 0.5)
                        wrapMode: Text.WordWrap
                        text: catalog.i18nc("@label", "Address")
                    }
                    Label
                    {
                        width: Math.round(parent.width * 0.5)
                        wrapMode: Text.WordWrap
                        text: base.selectedDevice ? base.selectedDevice.ipAddress : ""
                    }
                }

                Label
                {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text:{
                        // The property cluster size does not exist for older UM3 devices.
                        if(!base.selectedDevice || base.selectedDevice.clusterSize == null || base.selectedDevice.clusterSize == 1)
                        {
                            return "";
                        }
                        else if (base.selectedDevice.clusterSize === 0)
                        {
                            return catalog.i18nc("@label", "This printer is not set up to host a group of printers.");
                        }
                        else
                        {
                            return catalog.i18nc("@label", "This printer is the host for a group of %1 printers.".arg(base.selectedDevice.clusterSize));
                        }
                    }

                }
                Label
                {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    visible: base.selectedDevice != null && !base.completeProperties
                    text: catalog.i18nc("@label", "The printer at this address has not yet responded." )
                }

                Button
                {
                    text: catalog.i18nc("@action:button", "Connect")
                    enabled: (base.selectedDevice && base.completeProperties && base.selectedDevice.clusterSize > 0) ? true : false
                    onClicked: connectToPrinter()
                }
            }
        }
    }

    UM.Dialog
    {
        id: manualPrinterDialog
        property string printerKey
        property alias addressText: addressField.text

        title: catalog.i18nc("@title:window", "Printer Address")

        minimumWidth: 400 * screenScaleFactor
        minimumHeight: 130 * screenScaleFactor
        width: minimumWidth
        height: minimumHeight

        signal showDialog(string key, string address)
        onShowDialog:
        {
            printerKey = key;
            addressText = address;
            manualPrinterDialog.show();
            addressField.selectAll();
            addressField.focus = true;
        }

        Column {
            anchors.fill: parent
            spacing: UM.Theme.getSize("default_margin").height

            Label
            {
                text: catalog.i18nc("@alabel","Enter the IP address or hostname of your printer on the network.")
                width: parent.width
                wrapMode: Text.WordWrap
            }

            TextField
            {
                id: addressField
                width: parent.width
                validator: RegExpValidator
                {
                    regExp: /[a-zA-Z0-9\.\-\_]*/
                }

                onAccepted: btnOk.clicked()
            }
        }

        rightButtons: [
            Button {
                text: catalog.i18nc("@action:button","Cancel")
                onClicked:
                {
                    manualPrinterDialog.reject()
                    manualPrinterDialog.hide()
                }
            },
            Button {
                id: btnOk
                text: catalog.i18nc("@action:button", "OK")
                onClicked:
                {
                    manager.setManualDevice(manualPrinterDialog.printerKey, manualPrinterDialog.addressText)
                    manualPrinterDialog.hide()
                }
                enabled: manualPrinterDialog.addressText.trim() != ""
                isDefault: true
            }
        ]
    }
}
