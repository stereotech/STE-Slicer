// Copyright (c) 2018 Ultimaker B.V.
// Uranium is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Layouts 1.3
import QtQuick.Dialogs 1.2

import UM 1.2 as UM
import Cura 1.0 as Cura


Item
{
    id: base

    property QtObject qualityManager: CuraApplication.getQualityManager()
    property var resetEnabled: false  // Keep PreferencesDialog happy
    property var extrudersModel: Cura.ExtrudersModel {}

    UM.I18nCatalog { id: catalog; name: "cura"; }

    Cura.QualityManagementModel {
        id: qualitiesModel
    }

    Label {
        id: titleLabel
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            margins: 5 * screenScaleFactor
        }
        font.pointSize: 18
        text: catalog.i18nc("@title:tab", "Profiles")
    }

    property var hasCurrentItem: base.currentItem != null

    property var currentItem: {
        var current_index = qualityListView.currentIndex;
        return (current_index == -1) ? null : qualitiesModel.getItem(current_index);
    }

    property var currentItemName: hasCurrentItem ? base.currentItem.name : ""

    property var isCurrentItemActivated: {
        if (!base.currentItem) {
            return false;
        }
        return base.currentItem.name == Cura.MachineManager.activeQualityOrQualityChangesName;
    }

    property var canCreateProfile: {
        return isCurrentItemActivated && Cura.MachineManager.hasUserSettings;
    }

    Row  // Button Row
    {
        id: buttonRow
        anchors {
            left: parent.left
            right: parent.right
            top: titleLabel.bottom
        }
        height: childrenRect.height

        // Activate button
        Button
        {
            text: catalog.i18nc("@action:button", "Activate")
            iconName: "list-activate"
            enabled: !isCurrentItemActivated
            onClicked: {
                if (base.currentItem.is_read_only) {
                    Cura.MachineManager.setQualityGroup(base.currentItem.quality_group);
                } else {
                    Cura.MachineManager.setQualityChangesGroup(base.currentItem.quality_changes_group);
                }
            }
        }

        // Create button
        Button
        {
            text: catalog.i18nc("@label", "Create")
            iconName: "list-add"
            enabled: base.canCreateProfile && !Cura.MachineManager.stacksHaveErrors
            visible: base.canCreateProfile

            onClicked: {
                createQualityDialog.object = Cura.ContainerManager.makeUniqueName(base.currentItem.name);
                createQualityDialog.open();
                createQualityDialog.selectText();
            }
        }

        // Duplicate button
        Button
        {
            text: catalog.i18nc("@label", "Duplicate")
            iconName: "list-add"
            enabled: !base.canCreateProfile
            visible: !base.canCreateProfile

            onClicked: {
                duplicateQualityDialog.object = Cura.ContainerManager.makeUniqueName(base.currentItem.name);
                duplicateQualityDialog.open();
                duplicateQualityDialog.selectText();
            }
        }

        // Remove button
        Button
        {
            text: catalog.i18nc("@action:button", "Remove")
            iconName: "list-remove"
            enabled: base.hasCurrentItem && !base.currentItem.is_read_only && !base.isCurrentItemActivated
            onClicked: {
                forceActiveFocus();
                confirmRemoveQualityDialog.open();
            }
        }

        // Rename button
        Button
        {
            text: catalog.i18nc("@action:button", "Rename")
            iconName: "edit-rename"
            enabled: base.hasCurrentItem && !base.currentItem.is_read_only
            onClicked: {
                renameQualityDialog.object = base.currentItem.name;
                renameQualityDialog.open();
                renameQualityDialog.selectText();
            }
        }

        // Import button
        Button
        {
            text: catalog.i18nc("@action:button", "Import")
            iconName: "document-import"
            onClicked: {
                importDialog.open();
            }
        }

        // Export button
        Button
        {
            text: catalog.i18nc("@action:button", "Export")
            iconName: "document-export"
            enabled: base.hasCurrentItem && !base.currentItem.is_read_only
            onClicked: {
                exportDialog.open();
            }
        }
    }

    // Click create profile from ... in Profile context menu
    signal createProfile()
    onCreateProfile:
    {
        createQualityDialog.object = Cura.ContainerManager.makeUniqueName(Cura.MachineManager.activeQualityOrQualityChangesName);
        createQualityDialog.open();
        createQualityDialog.selectText();
    }

    // Dialog to request a name when creating a new profile
    UM.RenameDialog
    {
        id: createQualityDialog
        title: catalog.i18nc("@title:window", "Create Profile")
        object: "<new name>"
        onAccepted:
        {
            base.newQualityNameToSelect = newName;  // We want to switch to the new profile once it's created
            base.toActivateNewQuality = true;
            base.qualityManager.createQualityChanges(newName);
        }
    }

    property string newQualityNameToSelect: ""
    property bool toActivateNewQuality: false

    // This connection makes sure that we will switch to the correct quality after the model gets updated
    Connections
    {
        target: qualitiesModel
        onItemsChanged: {
            var toSelectItemName = base.currentItem == null ? "" : base.currentItem.name;
            if (newQualityNameToSelect != "") {
                toSelectItemName = newQualityNameToSelect;
            }

            var newIdx = -1;  // Default to nothing if nothing can be found
            if (toSelectItemName != "") {
                // Select the required quality name if given
                for (var idx = 0; idx < qualitiesModel.rowCount(); ++idx) {
                    var item = qualitiesModel.getItem(idx);
                    if (item.name == toSelectItemName) {
                        // Switch to the newly created profile if needed
                        newIdx = idx;
                        if (base.toActivateNewQuality) {
                            // Activate this custom quality if required
                            Cura.MachineManager.setQualityChangesGroup(item.quality_changes_group);
                        }
                        break;
                    }
                }
            }
            qualityListView.currentIndex = newIdx;

            // Reset states
            base.newQualityNameToSelect = "";
            base.toActivateNewQuality = false;
        }
    }

    // Dialog to request a name when duplicating a new profile
    UM.RenameDialog
    {
        id: duplicateQualityDialog
        title: catalog.i18nc("@title:window", "Duplicate Profile")
        object: "<new name>"
        onAccepted:
        {
            base.qualityManager.duplicateQualityChanges(newName, base.currentItem);
        }
    }

    // Confirmation dialog for removing a profile
    MessageDialog
    {
        id: confirmRemoveQualityDialog

        icon: StandardIcon.Question;
        title: catalog.i18nc("@title:window", "Confirm Remove")
        text: catalog.i18nc("@label (%1 is object name)", "Are you sure you wish to remove %1? This cannot be undone!").arg(base.currentItemName)
        standardButtons: StandardButton.Yes | StandardButton.No
        modality: Qt.ApplicationModal

        onYes:
        {
            base.qualityManager.removeQualityChangesGroup(base.currentItem.quality_changes_group);
            // reset current item to the first if available
            qualityListView.currentIndex = -1;  // Reset selection.
        }
    }

    // Dialog to rename a quality profile
    UM.RenameDialog
    {
        id: renameQualityDialog
        title: catalog.i18nc("@title:window", "Rename Profile")
        object: "<new name>"
        onAccepted:
        {
            var actualNewName = base.qualityManager.renameQualityChangesGroup(base.currentItem.quality_changes_group, newName);
            base.newQualityNameToSelect = actualNewName;  // Select the new name after the model gets updated
        }
    }

    // Dialog for importing a quality profile
    FileDialog
    {
        id: importDialog
        title: catalog.i18nc("@title:window", "Import Profile")
        selectExisting: true
        nameFilters: qualitiesModel.getFileNameFilters("profile_reader")
        folder: CuraApplication.getDefaultPath("dialog_profile_path")
        onAccepted:
        {
            var result = Cura.ContainerManager.importProfile(fileUrl);
            messageDialog.text = result.message;
            if (result.status == "ok") {
                messageDialog.icon = StandardIcon.Information;
            }
            else if (result.status == "duplicate") {
                messageDialog.icon = StandardIcon.Warning;
            }
            else {
                messageDialog.icon = StandardIcon.Critical;
            }
            messageDialog.open();
            CuraApplication.setDefaultPath("dialog_profile_path", folder);
        }
    }

    // Dialog for exporting a quality profile
    FileDialog
    {
        id: exportDialog
        title: catalog.i18nc("@title:window", "Export Profile")
        selectExisting: false
        nameFilters: qualitiesModel.getFileNameFilters("profile_writer")
        folder: CuraApplication.getDefaultPath("dialog_profile_path")
        onAccepted:
        {
            var result = Cura.ContainerManager.exportQualityChangesGroup(base.currentItem.quality_changes_group,
                                                                         fileUrl, selectedNameFilter);

            if (result && result.status == "error") {
                messageDialog.icon = StandardIcon.Critical;
                messageDialog.text = result.message;
                messageDialog.open();
            }

            // else pop-up Message thing from python code
            CuraApplication.setDefaultPath("dialog_profile_path", folder);
        }
    }

    Item {
        id: contentsItem

        anchors {
            top: titleLabel.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: 5 * screenScaleFactor
            bottomMargin: 0
        }

        clip: true
    }

    Item
    {
        anchors {
            top: buttonRow.bottom
            topMargin: UM.Theme.getSize("default_margin").height
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        SystemPalette { id: palette }

        Label
        {
            id: captionLabel
            anchors {
                top: parent.top
                left: parent.left
            }
            visible: text != ""
            text: catalog.i18nc("@label %1 is printer name", "Printer: %1").arg(Cura.MachineManager.activeMachineName)
            width: profileScrollView.width
            elide: Text.ElideRight
        }

        ScrollView
        {
            id: profileScrollView
            anchors {
                top: captionLabel.visible ? captionLabel.bottom : parent.top
                topMargin: captionLabel.visible ? UM.Theme.getSize("default_margin").height : 0
                bottom: parent.bottom
                left: parent.left
            }

            Rectangle {
                parent: viewport
                anchors.fill: parent
                color: palette.light
            }

            width: true ? (parent.width * 0.4) | 0 : parent.width
            frameVisible: true

            ListView
            {
                id: qualityListView

                model: qualitiesModel

                Component.onCompleted:
                {
                    var selectedItemName = Cura.MachineManager.activeQualityOrQualityChangesName;

                    // Select the required quality name if given
                    for (var idx = 0; idx < qualitiesModel.rowCount(); idx++) {
                        var item = qualitiesModel.getItem(idx);
                        if (item.name == selectedItemName) {
                            currentIndex = idx;
                            break;
                        }
                    }
                }

                section.property: "is_read_only"
                section.delegate: Rectangle
                {
                    height: childrenRect.height

                    Label
                    {
                        anchors.left: parent.left
                        anchors.leftMargin: UM.Theme.getSize("default_lining").width
                        text: section == "true" ? catalog.i18nc("@label", "Protected profiles") : catalog.i18nc("@label", "Custom profiles")
                        font.bold: true
                    }
                }

                delegate: Rectangle
                {
                    width: profileScrollView.width
                    height: childrenRect.height

                    property bool isCurrentItem: ListView.isCurrentItem
                    color: isCurrentItem ? palette.highlight : (model.index % 2) ? palette.base : palette.alternateBase

                    Label
                    {
                        anchors.left: parent.left
                        anchors.leftMargin: UM.Theme.getSize("default_margin").width
                        anchors.right: parent.right
                        width: Math.floor((parent.width * 0.8))
                        text: model.name
                        elide: Text.ElideRight
                        font.italic: model.name == Cura.MachineManager.activeQualityOrQualityChangesName
                        color: parent.isCurrentItem ? palette.highlightedText : palette.text
                    }

                    MouseArea
                    {
                        anchors.fill: parent
                        onClicked: {
                            parent.ListView.view.currentIndex = model.index;
                        }
                    }
                }
            }
        }

        // details panel on the right
        Item
        {
            id: detailsPanel

            anchors {
                left: profileScrollView.right
                leftMargin: UM.Theme.getSize("default_margin").width
                top: parent.top
                bottom: parent.bottom
                right: parent.right
            }

            Item
            {
                anchors.fill: parent
                visible: base.currentItem != null

                Item    // Profile title Label
                {
                    id: profileName

                    width: parent.width
                    height: childrenRect.height

                    Label {
                        text: base.currentItemName
                        font: UM.Theme.getFont("large")
                    }
                }

                Flow {
                    id: currentSettingsActions
                    visible: base.hasCurrentItem && base.currentItem.name == Cura.MachineManager.activeQualityOrQualityChangesName
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: profileName.bottom
                    anchors.topMargin: UM.Theme.getSize("default_margin").height

                    Button
                    {
                        text: catalog.i18nc("@action:button", "Update profile with current settings/overrides")
                        enabled: Cura.MachineManager.hasUserSettings && !base.currentItem.is_read_only
                        onClicked: Cura.ContainerManager.updateQualityChanges()
                    }

                    Button
                    {
                        text: catalog.i18nc("@action:button", "Discard current changes");
                        enabled: Cura.MachineManager.hasUserSettings
                        onClicked: Cura.ContainerManager.clearUserContainers();
                    }
                }

                Column {
                    id: profileNotices
                    anchors.top: currentSettingsActions.visible ? currentSettingsActions.bottom : currentSettingsActions.anchors.top
                    anchors.topMargin: UM.Theme.getSize("default_margin").height
                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: UM.Theme.getSize("default_margin").height

                    Label {
                        id: defaultsMessage
                        visible: false
                        text: catalog.i18nc("@action:label", "This profile uses the defaults specified by the printer, so it has no settings/overrides in the list below.")
                        wrapMode: Text.WordWrap
                        width: parent.width
                    }
                    Label {
                        id: noCurrentSettingsMessage
                        visible: base.isCurrentItemActivated && !Cura.MachineManager.hasUserSettings
                        text: catalog.i18nc("@action:label", "Your current settings match the selected profile.")
                        wrapMode: Text.WordWrap
                        width: parent.width
                    }
                }


                TabView
                {
                    anchors.left: parent.left
                    anchors.top: profileNotices.visible ? profileNotices.bottom : profileNotices.anchors.top
                    anchors.topMargin: UM.Theme.getSize("default_margin").height
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom

                    currentIndex: 0

                    ProfileTab
                    {
                        title: catalog.i18nc("@title:tab", "Global Settings")
                        qualityItem: base.currentItem
                    }

                    Repeater
                    {
                        model: base.extrudersModel

                        ProfileTab
                        {
                            title: model.name
                            extruderPosition: model.index
                            qualityItem: base.currentItem
                        }
                    }
                }
            }
        }
    }
}
