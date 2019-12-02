// Copyright (c) 2016 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.2
import QtQuick.Controls 1.1
import QtQuick.Layouts 1.1
import QtQuick.Window 2.1

import UM 1.2 as UM
import Cura 1.0 as Cura


Cura.MachineAction
{
    anchors.fill: parent;

    Item
    {
        id: upgradeSelectionMachineAction
        anchors.fill: parent

        Label
        {
            id: pageTitle
            width: parent.width
            text: catalog.i18nc("@title", "Select Printer Upgrades")
            wrapMode: Text.WordWrap
            font.pointSize: 18;
        }

        Label
        {
            id: pageDescription
            anchors.top: pageTitle.bottom
            anchors.topMargin: UM.Theme.getSize("default_margin").height
            width: parent.width
            wrapMode: Text.WordWrap
            text: catalog.i18nc("@label","Please select any upgrades made to this Ultimaker 2.");
        }

        CheckBox
        {
            id: olssonBlockCheckBox
            anchors.top: pageDescription.bottom
            anchors.topMargin: UM.Theme.getSize("default_margin").height

            text: catalog.i18nc("@label", "Olsson Block")
            checked: manager.hasVariants
            onClicked: manager.hasVariants = checked

            Connections
            {
                target: manager
                onHasVariantsChanged: olssonBlockCheckBox.checked = manager.hasVariants
            }
        }

        UM.I18nCatalog { id: catalog; name: "cura"; }
    }
}