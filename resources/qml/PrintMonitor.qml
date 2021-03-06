

import QtQuick 2.7
import QtQuick.Controls 1.1
import QtQuick.Controls.Styles 1.1
import QtQuick.Layouts 1.1

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

import "PrinterOutput"

Column
{
    id: printMonitor
    property var connectedDevice: SteSlicer.MachineManager.printerOutputDevices.length >= 1 ? SteSlicer.MachineManager.printerOutputDevices[0] : null
    property var activePrinter: connectedDevice != null ? connectedDevice.activePrinter : null
    property var activePrintJob: activePrinter != null ? activePrinter.activePrintJob: null

    SteSlicer.ExtrudersModel
    {
        id: extrudersModel
        simpleNames: true
    }

    OutputDeviceHeader
    {
        outputDevice: connectedDevice
    }

    Rectangle
    {
        color: UM.Theme.getColor("sidebar_lining")
        width: parent.width
        height: childrenRect.height

        Flow
        {
            id: extrudersGrid
            spacing: UM.Theme.getSize("sidebar_lining_thin").width
            width: parent.width

            Repeater
            {
                id: extrudersRepeater
                model: activePrinter != null ? activePrinter.extruders : null

                ExtruderBox
                {
                    color: UM.Theme.getColor("sidebar")
                    width: index == machineExtruderCount.properties.value - 1 && index % 2 == 0 ? extrudersGrid.width : Math.round(extrudersGrid.width / 2 - UM.Theme.getSize("sidebar_lining_thin").width / 2)
                    extruderModel: modelData
                }
            }
        }
    }

    Rectangle
    {
        color: UM.Theme.getColor("sidebar_lining")
        width: parent.width
        height: UM.Theme.getSize("sidebar_lining_thin").width
    }

    HeatedBedBox
    {
        visible: {
            if(activePrinter != null && activePrinter.bedTemperature != -1)
            {
                return true
            }
            return false
        }
        printerModel: activePrinter
    }

    UM.SettingPropertyProvider
    {
        id: bedTemperature
        containerStack: SteSlicer.MachineManager.activeMachine
        key: "material_bed_temperature"
        watchedProperties: ["value", "minimum_value", "maximum_value", "resolve"]
        storeIndex: 0

        property var resolve: SteSlicer.MachineManager.activeStack != SteSlicer.MachineManager.activeMachine ? properties.resolve : "None"
    }

    UM.SettingPropertyProvider
    {
        id: machineExtruderCount
        containerStack: SteSlicer.MachineManager.activeMachine
        key: "machine_extruder_count"
        watchedProperties: ["value"]
    }

    ManualPrinterControl
    {
        printerModel: activePrinter
        visible: activePrinter != null ? activePrinter.canControlManually : false
    }


    MonitorSection
    {
        label: catalog.i18nc("@label", "Active print")
        width: base.width
        visible: activePrinter != null
    }


    MonitorItem
    {
        label: catalog.i18nc("@label", "Job Name")
        value: activePrintJob != null ? activePrintJob.name : ""
        width: base.width
        visible: activePrinter != null
    }

    MonitorItem
    {
        label: catalog.i18nc("@label", "Printing Time")
        value: activePrintJob != null ? getPrettyTime(activePrintJob.timeTotal) : ""
        width: base.width
        visible: activePrinter != null
    }

    MonitorItem
    {
        label: catalog.i18nc("@label", "Estimated time left")
        value: activePrintJob != null ? getPrettyTime(activePrintJob.timeTotal - activePrintJob.timeElapsed) : ""
        visible:
        {
            if(activePrintJob == null)
            {
                return false
            }

            return (activePrintJob.state == "printing" ||
                    activePrintJob.state == "resuming" ||
                    activePrintJob.state == "pausing" ||
                    activePrintJob.state == "paused")
        }
        width: base.width
    }
}
