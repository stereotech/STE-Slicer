// Copyright (c) 2018 Ultimaker B.V.
// Cura is released under the terms of the LGPLv3 or higher.

import QtQuick 2.7
import QtQuick.Controls 1.4

import UM 1.2 as UM
import Cura 1.0 as Cura

Menu
{
    id: menu
    title: catalog.i18nc("@label:category menu label", "Material")

    property int extruderIndex: 0

    Cura.FavoriteMaterialsModel
    {
        id: favoriteMaterialsModel
        extruderPosition: menu.extruderIndex
    }

    Cura.GenericMaterialsModel
    {
        id: genericMaterialsModel
        extruderPosition: menu.extruderIndex
    }

    Cura.MaterialBrandsModel
    {
        id: brandModel
        extruderPosition: menu.extruderIndex
    }

    MenuItem
    {
        text: catalog.i18nc("@label:category menu label", "Favorites")
        enabled: false
        visible: favoriteMaterialsModel.items.length > 0
    }
    Instantiator
    {
        model: favoriteMaterialsModel
        delegate: MenuItem
        {
            text: model.brand + " " + model.name
            checkable: true
            checked: model.root_material_id == Cura.MachineManager.currentRootMaterialId[extruderIndex]
            onTriggered: Cura.MachineManager.setMaterial(extruderIndex, model.container_node)
            exclusiveGroup: group
        }
        onObjectAdded: menu.insertItem(index, object)
        onObjectRemoved: menu.removeItem(object) // TODO: This ain't gonna work, removeItem() takes an index, not object
    }

    MenuSeparator {}

    Menu
    {
        id: genericMenu
        title: catalog.i18nc("@label:category menu label", "Generic")

        Instantiator
        {
            model: genericMaterialsModel
            delegate: MenuItem
            {
                text: model.name
                checkable: true
                checked: model.root_material_id == Cura.MachineManager.currentRootMaterialId[extruderIndex]
                exclusiveGroup: group
                onTriggered: Cura.MachineManager.setMaterial(extruderIndex, model.container_node)
            }
            onObjectAdded: genericMenu.insertItem(index, object)
            onObjectRemoved: genericMenu.removeItem(object) // TODO: This ain't gonna work, removeItem() takes an index, not object
        }
    }

    MenuSeparator {}

    Instantiator
    {
        model: brandModel
        Menu
        {
            id: brandMenu
            title: brandName
            property string brandName: model.name
            property var brandMaterials: model.material_types

            Instantiator
            {
                model: brandMaterials
                delegate: Menu
                {
                    id: brandMaterialsMenu
                    title: materialName
                    property string materialName: model.name
                    property var brandMaterialColors: model.colors

                    Instantiator
                    {
                        model: brandMaterialColors
                        delegate: MenuItem
                        {
                            text: model.name
                            checkable: true
                            checked: model.id == Cura.MachineManager.allActiveMaterialIds[Cura.ExtruderManager.extruderIds[extruderIndex]]
                            exclusiveGroup: group
                            onTriggered: Cura.MachineManager.setMaterial(extruderIndex, model.container_node)
                        }
                        onObjectAdded: brandMaterialsMenu.insertItem(index, object)
                        onObjectRemoved: brandMaterialsMenu.removeItem(object)
                    }
                }
                onObjectAdded: brandMenu.insertItem(index, object)
                onObjectRemoved: brandMenu.removeItem(object)
            }
        }
        onObjectAdded: menu.insertItem(index, object)
        onObjectRemoved: menu.removeItem(object)
    }

    ExclusiveGroup {
        id: group
    }

    MenuSeparator {}

    MenuItem
    {
        action: Cura.Actions.manageMaterials
    }
}
