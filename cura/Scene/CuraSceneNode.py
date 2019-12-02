# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from copy import deepcopy
from typing import cast, Dict, List, Optional

from UM.Application import Application
from UM.Math.AxisAlignedBox import AxisAlignedBox
from UM.Math.Polygon import Polygon #For typing.
from UM.Scene.SceneNode import SceneNode
from UM.Scene.SceneNodeDecorator import SceneNodeDecorator #To cast the deepcopy of every decorator back to SceneNodeDecorator.

import cura.CuraApplication #To get the build plate.
from cura.Settings.ExtruderStack import ExtruderStack #For typing.
from cura.Settings.SettingOverrideDecorator import SettingOverrideDecorator #For per-object settings.

##  Scene nodes that are models are only seen when selecting the corresponding build plate
#   Note that many other nodes can just be UM SceneNode objects.
class CuraSceneNode(SceneNode):
    def __init__(self, parent: Optional["SceneNode"] = None, visible: bool = True, name: str = "", no_setting_override: bool = False) -> None:
        super().__init__(parent = parent, visible = visible, name = name)
        if not no_setting_override:
            self.addDecorator(SettingOverrideDecorator())  # now we always have a getActiveExtruderPosition, unless explicitly disabled
        self._outside_buildarea = False

    def setOutsideBuildArea(self, new_value: bool) -> None:
        self._outside_buildarea = new_value

    def isOutsideBuildArea(self) -> bool:
        return self._outside_buildarea or self.callDecoration("getBuildPlateNumber") < 0

    def isVisible(self) -> bool:
        return super().isVisible() and self.callDecoration("getBuildPlateNumber") == cura.CuraApplication.CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate

    def isSelectable(self) -> bool:
        return super().isSelectable() and self.callDecoration("getBuildPlateNumber") == cura.CuraApplication.CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate

    ##  Get the extruder used to print this node. If there is no active node, then the extruder in position zero is returned
    #   TODO The best way to do it is by adding the setActiveExtruder decorator to every node when is loaded
    def getPrintingExtruder(self) -> Optional[ExtruderStack]:
        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if global_container_stack is None:
            return None

        per_mesh_stack = self.callDecoration("getStack")
        extruders = list(global_container_stack.extruders.values())

        # Use the support extruder instead of the active extruder if this is a support_mesh
        if per_mesh_stack:
            if per_mesh_stack.getProperty("support_mesh", "value"):
                return extruders[int(global_container_stack.getExtruderPositionValueWithDefault("support_extruder_nr"))]

        # It's only set if you explicitly choose an extruder
        extruder_id = self.callDecoration("getActiveExtruder")

        for extruder in extruders:
            # Find out the extruder if we know the id.
            if extruder_id is not None:
                if extruder_id == extruder.getId():
                    return extruder
            else: # If the id is unknown, then return the extruder in the position 0
                try:
                    if extruder.getMetaDataEntry("position", default = "0") == "0":  # Check if the position is zero
                        return extruder
                except ValueError:
                    continue

        # This point should never be reached
        return None

    ##  Return the color of the material used to print this model
    def getDiffuseColor(self) -> List[float]:
        printing_extruder = self.getPrintingExtruder()

        material_color = "#808080"  # Fallback color
        if printing_extruder is not None and printing_extruder.material:
            material_color = printing_extruder.material.getMetaDataEntry("color_code", default = material_color)

        # Colors are passed as rgb hex strings (eg "#ffffff"), and the shader needs
        # an rgba list of floats (eg [1.0, 1.0, 1.0, 1.0])
        return [
            int(material_color[1:3], 16) / 255,
            int(material_color[3:5], 16) / 255,
            int(material_color[5:7], 16) / 255,
            1.0
        ]

    ##  Return if the provided bbox collides with the bbox of this scene node
    def collidesWithBbox(self, check_bbox: AxisAlignedBox) -> bool:
        bbox = self.getBoundingBox()
        if bbox is not None:
            # Mark the node as outside the build volume if the bounding box test fails.
            if check_bbox.intersectsBox(bbox) != AxisAlignedBox.IntersectionResult.FullIntersection:
                return True

        return False

    ##  Return if any area collides with the convex hull of this scene node
    def collidesWithArea(self, areas: List[Polygon]) -> bool:
        convex_hull = self.callDecoration("getConvexHull")
        if convex_hull:
            if not convex_hull.isValid():
                return False

            # Check for collisions between disallowed areas and the object
            for area in areas:
                overlap = convex_hull.intersectsPolygon(area)
                if overlap is None:
                    continue
                return True
        return False

    ##  Override of SceneNode._calculateAABB to exclude non-printing-meshes from bounding box
    def _calculateAABB(self) -> None:
        if self._mesh_data:
            aabb = self._mesh_data.getExtents(self.getWorldTransformation())
        else:  # If there is no mesh_data, use a boundingbox that encompasses the local (0,0,0)
            position = self.getWorldPosition()
            aabb = AxisAlignedBox(minimum = position, maximum = position)

        for child in self._children:
            if child.callDecoration("isNonPrintingMesh"):
                # Non-printing-meshes inside a group should not affect push apart or drop to build plate
                continue
            if aabb is None:
                aabb = child.getBoundingBox()
            else:
                aabb = aabb + child.getBoundingBox()
        self._aabb = aabb

    ##  Taken from SceneNode, but replaced SceneNode with CuraSceneNode
    def __deepcopy__(self, memo: Dict[int, object]) -> "CuraSceneNode":
        copy = CuraSceneNode(no_setting_override = True)  # Setting override will be added later
        copy.setTransformation(self.getLocalTransformation())
        copy.setMeshData(self._mesh_data)
        copy.setVisible(cast(bool, deepcopy(self._visible, memo)))
        copy._selectable = cast(bool, deepcopy(self._selectable, memo))
        copy._name = cast(str, deepcopy(self._name, memo))
        for decorator in self._decorators:
            copy.addDecorator(cast(SceneNodeDecorator, deepcopy(decorator, memo)))

        for child in self._children:
            copy.addChild(cast(SceneNode, deepcopy(child, memo)))
        self.calculateBoundingBoxMesh()
        return copy

    def transformChanged(self) -> None:
        self._transformChanged()
