

import QtQuick 2.2

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Item
{
    property var status: "disconnected"
    width: childrenRect.width
    height: childrenRect.height
    UM.RecolorImage
    {
        id: statusIcon
        width: UM.Theme.getSize("printer_status_icon").width
        height: UM.Theme.getSize("printer_status_icon").height
        sourceSize.width: width
        sourceSize.height: width
        color: UM.Theme.getColor("tab_status_" + parent.status)
        source: UM.Theme.getIcon(parent.status)
    }
}



