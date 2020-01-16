

import QtQuick 2.2
import QtQuick.Controls 1.1
import QtQuick.Layouts 1.1
import QtQuick.Window 2.1
import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Item {
    id: base;
    property string activeQualityDefinitionId: SteSlicer.MachineManager.activeQualityDefinitionId;
    property bool isUM3: activeQualityDefinitionId == "ultimaker3" || activeQualityDefinitionId.match("ultimaker_") != null;
    property bool printerConnected: SteSlicer.MachineManager.printerConnected;
    property bool printerAcceptsCommands: printerConnected && SteSlicer.MachineManager.printerOutputDevices[0].acceptsCommands;
    property bool authenticationRequested: printerConnected && (SteSlicer.MachineManager.printerOutputDevices[0].authenticationState == 2 || SteSlicer.MachineManager.printerOutputDevices[0].authenticationState == 5); // AuthState.AuthenticationRequested or AuthenticationReceived.

    UM.I18nCatalog {
        id: catalog;
        name: "steslicer";
    }

    Row {
        objectName: "networkPrinterConnectButton";
        spacing: UM.Theme.getSize("default_margin").width;
        visible: isUM3;

        Button {
            height: UM.Theme.getSize("save_button_save_to_button").height;
            onClicked: SteSlicer.MachineManager.printerOutputDevices[0].requestAuthentication();
            style: UM.Theme.styles.sidebar_action_button;
            text: catalog.i18nc("@action:button", "Request Access");
            tooltip: catalog.i18nc("@info:tooltip", "Send access request to the printer");
            visible: printerConnected && !printerAcceptsCommands && !authenticationRequested;
        }

        Button {
            height: UM.Theme.getSize("save_button_save_to_button").height;
            onClicked: connectActionDialog.show();
            style: UM.Theme.styles.sidebar_action_button;
            text: catalog.i18nc("@action:button", "Connect");
            tooltip: catalog.i18nc("@info:tooltip", "Connect to a printer");
            visible: !printerConnected;
        }
    }

    UM.Dialog {
        id: connectActionDialog;
        rightButtons: Button {
            iconName: "dialog-close";
            onClicked: connectActionDialog.reject();
            text: catalog.i18nc("@action:button", "Close");
        }

        Loader {
            anchors.fill: parent;
            source: "DiscoverUM3Action.qml";
        }
    }

    Column {
        anchors.fill: parent;
        objectName: "networkPrinterConnectionInfo";
        spacing: UM.Theme.getSize("default_margin").width;
        visible: isUM3;

        Button {
            onClicked: SteSlicer.MachineManager.printerOutputDevices[0].requestAuthentication();
            text: catalog.i18nc("@action:button", "Request Access");
            tooltip: catalog.i18nc("@info:tooltip", "Send access request to the printer");
            visible: printerConnected && !printerAcceptsCommands && !authenticationRequested;
        }

        Row {
            anchors {
                left: parent.left;
                right: parent.right;
            }
            height: childrenRect.height;
            spacing: UM.Theme.getSize("default_margin").width;
            visible: printerConnected;

            Column {
                Repeater {
                    model: SteSlicer.ExtrudersModel {
                        simpleNames: true;
                    }

                    Label {
                        text: model.name;
                    }
                }
            }

            Column {
                Repeater {
                    id: nozzleColumn;
                    model: printerConnected ? SteSlicer.MachineManager.printerOutputDevices[0].hotendIds : null;

                    Label {
                        text: nozzleColumn.model[index];
                    }
                }
            }

            Column {
                Repeater {
                    id: materialColumn;
                    model: printerConnected ? SteSlicer.MachineManager.printerOutputDevices[0].materialNames : null;

                    Label {
                        text: materialColumn.model[index];
                    }
                }
            }
        }

        Button {
            onClicked: manager.loadConfigurationFromPrinter();
            text: catalog.i18nc("@action:button", "Activate Configuration");
            tooltip: catalog.i18nc("@info:tooltip", "Load the configuration of the printer into STE Slicer");
            visible: false; // printerConnected && !isClusterPrinter()
        }
    }
}
