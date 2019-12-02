// Copyright (c) 2018 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.1
import QtQuick.Controls.Styles 1.1
import QtQuick.Layouts 1.1

import UM 1.1 as UM
import Cura 1.0 as Cura

Item {
    id: base;
    UM.I18nCatalog { id: catalog; name:"cura"}

    property real progress: UM.Backend.progress
    property int backendState: UM.Backend.state
    property bool activity: CuraApplication.platformActivity

    property alias buttonRowWidth: saveRow.width

    property string fileBaseName
    property string statusText:
    {
        if(!activity)
        {
            return catalog.i18nc("@label:PrintjobStatus", "Please load a 3D model");
        }

        if (base.backendState == "undefined") {
            return ""
        }

        switch(base.backendState)
        {
            case 1:
                return catalog.i18nc("@label:PrintjobStatus", "Ready to slice");
            case 2:
                return catalog.i18nc("@label:PrintjobStatus", "Slicing...");
            case 3:
                return catalog.i18nc("@label:PrintjobStatus %1 is target operation","Ready to %1").arg(UM.OutputDeviceManager.activeDeviceShortDescription);
            case 4:
                return catalog.i18nc("@label:PrintjobStatus", "Unable to Slice");
            case 5:
                return catalog.i18nc("@label:PrintjobStatus", "Slicing unavailable");
            default:
                return "";
        }
    }

    function sliceOrStopSlicing() {
        try {
            if ([1, 5].indexOf(base.backendState) != -1) {
                CuraApplication.backend.forceSlice();
            } else {
                CuraApplication.backend.stopSlicing();
            }
        } catch (e) {
            console.log('Could not start or stop slicing', e)
        }
    }

    Label {
        id: statusLabel
        width: parent.width - 2 * UM.Theme.getSize("sidebar_margin").width
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.leftMargin: UM.Theme.getSize("sidebar_margin").width

        color: UM.Theme.getColor("text")
        font: UM.Theme.getFont("default_bold")
        text: statusText;
    }

    Rectangle {
        id: progressBar
        width: parent.width - 2 * UM.Theme.getSize("sidebar_margin").width
        height: UM.Theme.getSize("progressbar").height
        anchors.top: statusLabel.bottom
        anchors.topMargin: Math.round(UM.Theme.getSize("sidebar_margin").height / 4)
        anchors.left: parent.left
        anchors.leftMargin: UM.Theme.getSize("sidebar_margin").width
        radius: UM.Theme.getSize("progressbar_radius").width
        color: UM.Theme.getColor("progressbar_background")

        Rectangle {
            width: Math.max(parent.width * base.progress)
            height: parent.height
            color: UM.Theme.getColor("progressbar_control")
            radius: UM.Theme.getSize("progressbar_radius").width
            visible: (base.backendState != "undefined" && base.backendState == 2) ? true : false
        }
    }

    // Shortcut for "save as/print/..."
    Action {
        shortcut: "Ctrl+P"
        onTriggered:
        {
            // only work when the button is enabled
            if (saveToButton.enabled) {
                saveToButton.clicked();
            }
            // prepare button
            if (prepareButton.enabled) {
                sliceOrStopSlicing();
            }
        }
    }

    Item {
        id: saveRow
        width: {
            // using childrenRect.width directly causes a binding loop, because setting the width affects the childrenRect
            var children_width = UM.Theme.getSize("default_margin").width;
            for (var index in children)
            {
                var child = children[index];
                if(child.visible)
                {
                    children_width += child.width + child.anchors.rightMargin;
                }
            }
            return Math.min(children_width, base.width - UM.Theme.getSize("sidebar_margin").width);
        }
        height: saveToButton.height
        anchors.bottom: parent.bottom
        anchors.bottomMargin: UM.Theme.getSize("sidebar_margin").height
        anchors.right: parent.right
        clip: true

        Row {
            id: additionalComponentsRow
            anchors.top: parent.top
            anchors.right: saveToButton.visible ? saveToButton.left : (prepareButton.visible ? prepareButton.left : parent.right)
            anchors.rightMargin: UM.Theme.getSize("default_margin").width

            spacing: UM.Theme.getSize("default_margin").width
        }

        Component.onCompleted: {
            saveRow.addAdditionalComponents("saveButton")
        }

        Connections {
            target: CuraApplication
            onAdditionalComponentsChanged: saveRow.addAdditionalComponents("saveButton")
        }

        function addAdditionalComponents (areaId) {
            if(areaId == "saveButton") {
                for (var component in CuraApplication.additionalComponents["saveButton"]) {
                    CuraApplication.additionalComponents["saveButton"][component].parent = additionalComponentsRow
                }
            }
        }

        Connections {
            target: UM.Preferences
            onPreferenceChanged:
            {
                var autoSlice = UM.Preferences.getValue("general/auto_slice");
                prepareButton.autoSlice = autoSlice;
                saveToButton.autoSlice = autoSlice;
            }
        }

        // Prepare button, only shows if auto_slice is off
        Button {
            id: prepareButton

            tooltip: [1, 5].indexOf(base.backendState) != -1 ? catalog.i18nc("@info:tooltip","Slice current printjob") : catalog.i18nc("@info:tooltip","Cancel slicing process")
            // 1 = not started, 2 = Processing
            enabled: base.backendState != "undefined" && ([1, 2].indexOf(base.backendState) != -1) && base.activity
            visible: base.backendState != "undefined" && !autoSlice && ([1, 2, 4].indexOf(base.backendState) != -1) && base.activity
            property bool autoSlice
            height: UM.Theme.getSize("save_button_save_to_button").height

            anchors.top: parent.top
            anchors.right: parent.right
            anchors.rightMargin: UM.Theme.getSize("sidebar_margin").width

            // 1 = not started, 4 = error, 5 = disabled
            text: [1, 4, 5].indexOf(base.backendState) != -1 ? catalog.i18nc("@label:Printjob", "Prepare") : catalog.i18nc("@label:Printjob", "Cancel")
            onClicked:
            {
                sliceOrStopSlicing();
            }

            style: ButtonStyle {
                background: Rectangle
                {
                    border.width: UM.Theme.getSize("default_lining").width
                    border.color:
                    {
                        if(!control.enabled)
                            return UM.Theme.getColor("action_button_disabled_border");
                        else if(control.pressed)
                            return UM.Theme.getColor("action_button_active_border");
                        else if(control.hovered)
                            return UM.Theme.getColor("action_button_hovered_border");
                        else
                            return UM.Theme.getColor("action_button_border");
                    }
                    color:
                    {
                        if(!control.enabled)
                            return UM.Theme.getColor("action_button_disabled");
                        else if(control.pressed)
                            return UM.Theme.getColor("action_button_active");
                        else if(control.hovered)
                            return UM.Theme.getColor("action_button_hovered");
                        else
                            return UM.Theme.getColor("action_button");
                    }

                    Behavior on color { ColorAnimation { duration: 50; } }

                    implicitWidth: actualLabel.contentWidth + (UM.Theme.getSize("sidebar_margin").width * 2)

                    Label {
                        id: actualLabel
                        anchors.centerIn: parent
                        color:
                        {
                            if(!control.enabled)
                                return UM.Theme.getColor("action_button_disabled_text");
                            else if(control.pressed)
                                return UM.Theme.getColor("action_button_active_text");
                            else if(control.hovered)
                                return UM.Theme.getColor("action_button_hovered_text");
                            else
                                return UM.Theme.getColor("action_button_text");
                        }
                        font: UM.Theme.getFont("action_button")
                        text: control.text;
                    }
                }
                label: Item { }
            }
        }

        Button {
            id: saveToButton

            tooltip: UM.OutputDeviceManager.activeDeviceDescription;
            // 3 = done, 5 = disabled
            enabled: base.backendState != "undefined" && (base.backendState == 3 || base.backendState == 5) && base.activity == true
            visible: base.backendState != "undefined" && autoSlice || ((base.backendState == 3 || base.backendState == 5) && base.activity == true)
            property bool autoSlice
            height: UM.Theme.getSize("save_button_save_to_button").height

            anchors.top: parent.top
            anchors.right: deviceSelectionMenu.visible ? deviceSelectionMenu.left : parent.right
            anchors.rightMargin: deviceSelectionMenu.visible ? -3 * UM.Theme.getSize("default_lining").width : UM.Theme.getSize("sidebar_margin").width

            text: UM.OutputDeviceManager.activeDeviceShortDescription
            onClicked:
            {
                forceActiveFocus();
                UM.OutputDeviceManager.requestWriteToDevice(UM.OutputDeviceManager.activeDevice, PrintInformation.jobName,
                    { "filter_by_machine": true, "preferred_mimetypes": Cura.MachineManager.activeMachine.preferred_output_file_formats });
            }

            style: ButtonStyle {
                background: Rectangle
                {
                    border.width: UM.Theme.getSize("default_lining").width
                    border.color:
                    {
                        if(!control.enabled)
                            return UM.Theme.getColor("action_button_disabled_border");
                        else if(control.pressed)
                            return UM.Theme.getColor("print_button_ready_pressed_border");
                        else if(control.hovered)
                            return UM.Theme.getColor("print_button_ready_hovered_border");
                        else
                            return UM.Theme.getColor("print_button_ready_border");
                    }
                    color:
                    {
                        if(!control.enabled)
                            return UM.Theme.getColor("action_button_disabled");
                        else if(control.pressed)
                            return UM.Theme.getColor("print_button_ready_pressed");
                        else if(control.hovered)
                            return UM.Theme.getColor("print_button_ready_hovered");
                        else
                            return UM.Theme.getColor("print_button_ready");
                    }

                    Behavior on color { ColorAnimation { duration: 50; } }

                    implicitWidth: actualLabel.contentWidth + (UM.Theme.getSize("sidebar_margin").width * 2)

                    Label {
                        id: actualLabel
                        anchors.centerIn: parent
                        color:
                        {
                            if(!control.enabled)
                                return UM.Theme.getColor("action_button_disabled_text");
                            else if(control.pressed)
                                return UM.Theme.getColor("print_button_ready_text");
                            else if(control.hovered)
                                return UM.Theme.getColor("print_button_ready_text");
                            else
                                return UM.Theme.getColor("print_button_ready_text");
                        }
                        font: UM.Theme.getFont("action_button")
                        text: control.text;
                    }
                }
                label: Item { }
            }
        }

        Button {
            id: deviceSelectionMenu
            tooltip: catalog.i18nc("@info:tooltip","Select the active output device");
            anchors.top: parent.top
            anchors.right: parent.right

            anchors.rightMargin: UM.Theme.getSize("sidebar_margin").width
            width: UM.Theme.getSize("save_button_save_to_button").height
            height: UM.Theme.getSize("save_button_save_to_button").height
            // 3 = Done, 5 = Disabled
            enabled: base.backendState != "undefined" && (base.backendState == 3 || base.backendState == 5) && base.activity == true
            visible: base.backendState != "undefined" && (devicesModel.deviceCount > 1) && (base.backendState == 3 || base.backendState == 5) && base.activity == true


            style: ButtonStyle {
                background: Rectangle {
                    id: deviceSelectionIcon
                    border.width: UM.Theme.getSize("default_lining").width
                    border.color:
                    {
                        if(!control.enabled)
                            return UM.Theme.getColor("action_button_disabled_border");
                        else if(control.pressed)
                            return UM.Theme.getColor("print_button_ready_pressed_border");
                        else if(control.hovered)
                            return UM.Theme.getColor("print_button_ready_hovered_border");
                        else
                            return UM.Theme.getColor("print_button_ready_border");
                    }
                    color:
                    {
                        if(!control.enabled)
                            return UM.Theme.getColor("action_button_disabled");
                        else if(control.pressed)
                            return UM.Theme.getColor("print_button_ready_pressed");
                        else if(control.hovered)
                            return UM.Theme.getColor("print_button_ready_hovered");
                        else
                            return UM.Theme.getColor("print_button_ready");
                    }
                    Behavior on color { ColorAnimation { duration: 50; } }
                    anchors.left: parent.left
                    anchors.leftMargin: Math.round(UM.Theme.getSize("save_button_text_margin").width / 2);
                    width: parent.height
                    height: parent.height

                    UM.RecolorImage {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: UM.Theme.getSize("standard_arrow").width
                        height: UM.Theme.getSize("standard_arrow").height
                        sourceSize.width: width
                        sourceSize.height: height
                        color:
                        {
                            if(!control.enabled)
                                return UM.Theme.getColor("action_button_disabled_text");
                            else if(control.pressed)
                                return UM.Theme.getColor("print_button_ready_text");
                            else if(control.hovered)
                                return UM.Theme.getColor("print_button_ready_text");
                            else
                                return UM.Theme.getColor("print_button_ready_text");
                        }
                        source: UM.Theme.getIcon("arrow_bottom");
                    }
                }
                label: Label{ }
            }

            menu: Menu {
                id: devicesMenu;
                Instantiator {
                    model: devicesModel;
                    MenuItem {
                        text: model.description
                        checkable: true;
                        checked: model.id == UM.OutputDeviceManager.activeDevice;
                        exclusiveGroup: devicesMenuGroup;
                        onTriggered: {
                            UM.OutputDeviceManager.setActiveDevice(model.id);
                        }
                    }
                    onObjectAdded: devicesMenu.insertItem(index, object)
                    onObjectRemoved: devicesMenu.removeItem(object)
                }
                ExclusiveGroup { id: devicesMenuGroup; }
            }
        }
        UM.OutputDevicesModel { id: devicesModel; }
    }
}
