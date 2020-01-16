

import QtQuick 2.2
import QtQuick.Controls 1.1
import QtQuick.Controls.Styles 1.1
import QtQuick.Layouts 1.1

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Item
{
    id: base
    property string label
    height: childrenRect.height;
    Rectangle
    {
        color: UM.Theme.getColor("setting_category")
        width: base.width
        height: UM.Theme.getSize("section").height

        Label
        {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: UM.Theme.getSize("default_margin").width
            text: label
            font: UM.Theme.getFont("setting_category")
            color: UM.Theme.getColor("setting_category_text")
        }
    }
}