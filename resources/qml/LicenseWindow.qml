

import QtQuick 2.2
import QtQuick.Controls 1.4

import UM 1.3 as UM

UM.Dialog
{
    id: baseDialog
    flags: Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint;
    minimumWidth: Math.round(UM.Theme.getSize("modal_window_minimum").width * 0.75)
    minimumHeight: Math.round(UM.Theme.getSize("modal_window_minimum").height * 0.5)
    width: minimumWidth
    height: minimumHeight
    title: catalog.i18nc("@title:window", "Enter License Key")

    TextArea
    {
        id: licenseField
        anchors.top: parent.top
        width: parent.width
        anchors.bottom: buttonRow.top
        text: manager.licenseKey
        onTextChanged: manager.licenseKey = text
    }

    Item
    {
        id: buttonRow
        anchors.bottom: parent.bottom
        width: parent.width
        anchors.bottomMargin: UM.Theme.getSize("default_margin").height

        UM.I18nCatalog { id: catalog; name:"steslicer" }

        Button
        {
            anchors.right: parent.right
            text: catalog.i18nc("@action:button", "Enter Key")
            onClicked: {
                baseDialog.accepted()
            }
            enabled: manager.licenseValid
        }

        Label
        {
            anchors.verticalCenter: buttonRow.verticalCenter
            anchors.horizontalCenter: buttonRow.horizontalCenter
            anchors.verticalCenterOffset: 20
            font.bold: true
            color: manager.licenseValid ? "green" : "red"
            text: manager.licenseValid ? catalog.i18nc("@label","License is valid!") : catalog.i18nc("@label","License is invalid!")
        }

        Button
        {
            anchors.left: parent.left
            text: catalog.i18nc("@action:button", "Enter Later")
            onClicked: {
                baseDialog.rejected()
            }
        }
    }

    onAccepted: manager.enterLater(true)
    onRejected: manager.enterLater(true)
    onClosing: manager.enterLater(false)
}
