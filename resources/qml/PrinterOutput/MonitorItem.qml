

import QtQuick 2.2
import QtQuick.Controls 1.1
import QtQuick.Controls.Styles 1.1
import QtQuick.Layouts 1.1

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Item
{
    property string label: ""
    property string value: ""
    height: childrenRect.height;

    Row
    {
        height: UM.Theme.getSize("setting_control").height
        width: Math.floor(base.width - 2 * UM.Theme.getSize("default_margin").width)
        anchors.left: parent.left
        anchors.leftMargin: UM.Theme.getSize("default_margin").width

        Label
        {
            width: Math.floor(parent.width * 0.4)
            anchors.verticalCenter: parent.verticalCenter
            text: label
            color: connectedPrinter != null && connectedPrinter.acceptsCommands ? UM.Theme.getColor("setting_control_text") : UM.Theme.getColor("setting_control_disabled_text")
            font: UM.Theme.getFont("default")
            elide: Text.ElideRight
        }
        Label
        {
            width: Math.floor(parent.width * 0.6)
            anchors.verticalCenter: parent.verticalCenter
            text: value
            color: connectedPrinter != null && connectedPrinter.acceptsCommands ? UM.Theme.getColor("setting_control_text") : UM.Theme.getColor("setting_control_disabled_text")
            font: UM.Theme.getFont("default")
            elide: Text.ElideRight
        }
    }
}