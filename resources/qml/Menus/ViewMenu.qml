

import QtQuick 2.2
import QtQuick.Controls 1.1

import UM 1.2 as UM
import SteSlicer 1.0 as SteSlicer

Menu
{
    title: catalog.i18nc("@title:menu menubar:toplevel", "&View")
    id: base

    property var multiBuildPlateModel: SteSlicerApplication.getMultiBuildPlateModel()

    // main views
    Instantiator
    {
        model: UM.ViewModel{}
        MenuItem
        {
            text: model.name
            checkable: true
            checked: model.active
            exclusiveGroup: group
            onTriggered: UM.Controller.setActiveView(model.id)
            enabled: !PrintInformation.preSliced
        }
        onObjectAdded: base.insertItem(index, object)
        onObjectRemoved: base.removeItem(object)
    }
    ExclusiveGroup
    {
        id: group
    }

    MenuSeparator {}

    Menu
    {
        title: catalog.i18nc("@action:inmenu menubar:view","&Camera position");
        MenuItem { action: SteSlicer.Actions.view3DCamera; }
        MenuItem { action: SteSlicer.Actions.viewFrontCamera; }
        MenuItem { action: SteSlicer.Actions.viewTopCamera; }
        MenuItem { action: SteSlicer.Actions.viewLeftSideCamera; }
        MenuItem { action: SteSlicer.Actions.viewRightSideCamera; }
    }

    MenuSeparator
    {
        visible: UM.Preferences.getValue("steslicer/use_multi_build_plate")
    }

    Menu
    {
        id: buildPlateMenu;
        title: catalog.i18nc("@action:inmenu menubar:view","&Build plate")
        visible: UM.Preferences.getValue("steslicer/use_multi_build_plate")
        Instantiator
        {
            model: base.multiBuildPlateModel
            MenuItem
            {
                text: base.multiBuildPlateModel.getItem(index).name;
                onTriggered: SteSlicer.SceneController.setActiveBuildPlate(base.multiBuildPlateModel.getItem(index).buildPlateNumber)
                checkable: true
                checked: base.multiBuildPlateModel.getItem(index).buildPlateNumber == base.multiBuildPlateModel.activeBuildPlate
                exclusiveGroup: buildPlateGroup
                visible: UM.Preferences.getValue("steslicer/use_multi_build_plate")
            }
            onObjectAdded: buildPlateMenu.insertItem(index, object)
            onObjectRemoved: buildPlateMenu.removeItem(object)
        }
        ExclusiveGroup
        {
            id: buildPlateGroup
        }
    }

    MenuSeparator {}

    MenuItem
    {
        action: SteSlicer.Actions.expandSidebar
    }

    MenuSeparator {}
    MenuItem
    {
        action: SteSlicer.Actions.toggleFullScreen
    }
}
