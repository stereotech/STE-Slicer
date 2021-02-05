from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

from UM.Application import Application
from UM.Logger import Logger
from UM.Math.Vector import Vector
from UM.Tool import Tool
from UM.Event import Event, MouseEvent
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Scene.Selection import Selection

from steslicer.Scene.SplittingPlaneDecorator import SplittingPlaneDecorator
from steslicer.Settings.ExtruderManager import ExtruderManager
from steslicer.SteSlicerApplication import SteSlicerApplication
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode
from steslicer.PickingPass import PickingPass

from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from steslicer.Operations.SetParentOperation import SetParentOperation

from steslicer.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from steslicer.Scene.BuildPlateDecorator import BuildPlateDecorator

from UM.Settings.SettingInstance import SettingInstance

import trimesh
import numpy

class PlaneSplitter(Tool):
    def __init__(self):
        super().__init__()
        self._shortcut_key = Qt.Key_P
        self._controller = self.getController()

        self._visible = False
        self._plane_size = 100

        self._selection_pass = None

        self._global_container_stack = None
        SteSlicerApplication.getInstance().globalContainerStackChanged.connect(self._onStackChanged)
        self._onStackChanged()
        self._printing_mode = None
        # Note: if the selection is cleared with this tool active, there is no way to switch to
        # another tool than to reselect an object (by clicking it) because the tool buttons in the
        # toolbar will have been disabled. That is why we need to ignore the first press event
        # after the selection has been cleared.
        Selection.selectionChanged.connect(self._onSelectionChanged)
        self._had_selection = False
        self._skip_press = False

        self._had_selection_timer = QTimer()
        self._had_selection_timer.setInterval(0)
        self._had_selection_timer.setSingleShot(True)
        self._had_selection_timer.timeout.connect(self._selectionChangeDelay)

    def event(self, event):
        super().event(event)
        modifiers = QApplication.keyboardModifiers()
        ctrl_is_active = modifiers & Qt.ControlModifier

        if event.type == Event.MousePressEvent and MouseEvent.LeftButton in event.buttons and self._controller.getToolsEnabled():
            if ctrl_is_active:
                self._controller.setActiveTool("TranslateTool")
                return

            if self._skip_press:
                # The selection was previously cleared, do not add/remove an anti-support mesh but
                # use this click for selection and reactivating this tool only.
                self._skip_press = False
                return

            if self._selection_pass is None:
                # The selection renderpass is used to identify objects in the current view
                self._selection_pass = Application.getInstance().getRenderer().getRenderPass("selection")
            picked_node = self._controller.getScene().findObject(self._selection_pass.getIdAtPosition(event.x, event.y))
            if not picked_node:
                # There is no slicable object at the picked location
                return

            node_stack = picked_node.callDecoration("getStack")
            if node_stack:
                if node_stack.getProperty("anti_overhang_mesh", "value"):
                    self._removeSplittingPlane(picked_node)
                    return

                elif node_stack.getProperty("support_mesh", "value") or node_stack.getProperty("infill_mesh",
                                                                                               "value") or node_stack.getProperty(
                        "cutting_mesh", "value"):
                    # Only "normal" meshes can have anti_overhang_meshes added to them
                    return

            # Create a pass for picking a world-space location from the mouse location
            active_camera = self._controller.getScene().getActiveCamera()
            picking_pass = PickingPass(active_camera.getViewportWidth(), active_camera.getViewportHeight())
            picking_pass.render()

            picked_position = picking_pass.getPickedPosition(event.x, event.y)

            # Add the anti_overhang_mesh cube at the picked location
            self._createEraserMesh(picked_node, picked_position)

    def _createEraserMesh(self, parent: SteSlicerSceneNode, position: Vector):
        node = SteSlicerSceneNode()

        node.setName("SplittingPlane")
        node.setSelectable(True)
        mesh = self._createPlane(self._plane_size)
        node.setMeshData(mesh.build())

        active_build_plate = SteSlicerApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        node.addDecorator(BuildPlateDecorator(active_build_plate))
        node.addDecorator(SliceableObjectDecorator())
        node.addDecorator(SplittingPlaneDecorator())

        stack = node.callDecoration(
            "getStack")  # created by SettingOverrideDecorator that is automatically added to SteSlicerSceneNode
        settings = stack.getTop()

        definition = stack.getSettingDefinition("anti_overhang_mesh")
        new_instance = SettingInstance(definition, settings)
        new_instance.setProperty("value", True)
        new_instance.resetState()  # Ensure that the state is not seen as a user state.
        settings.addInstance(new_instance)

        op = GroupedOperation()
        # First add node to the scene at the correct position/scale, before parenting, so the eraser mesh does not get scaled with the parent
        op.addOperation(AddSceneNodeOperation(node, self._controller.getScene().getRoot()))
        op.addOperation(SetParentOperation(node, parent))
        op.push()
        node.setPosition(position, SteSlicerSceneNode.TransformSpace.World)

        SteSlicerApplication.getInstance().getController().getScene().sceneChanged.emit(node)

    def _removeSplittingPlane(self, node: SteSlicerSceneNode):
        parent = node.getParent()
        if parent == self._controller.getScene().getRoot():
            parent = None

        op = RemoveSceneNodeOperation(node)
        op.push()

        if parent and not Selection.isSelected(parent):
            Selection.add(parent)

        SteSlicerApplication.getInstance().getController().getScene().sceneChanged.emit(node)

    def _updateEnabled(self):
        plugin_enabled = False

        global_container_stack = SteSlicerApplication.getInstance().getGlobalContainerStack()
        if global_container_stack:
            plugin_enabled = global_container_stack.getProperty("printing_mode", "value") in ["discrete"]
            machine_width = global_container_stack.getProperty("machine_width", "value")
            machine_depth = global_container_stack.getProperty("machine_depth", "value")
            self._plane_size = max(machine_width, machine_depth, 100)
            
        SteSlicerApplication.getInstance().getController().toolEnabledChanged.emit(self._plugin_id, plugin_enabled)

    def _onSettingPropertyChanged(self, setting_key: str, property_name: str):
        if property_name != "value" and setting_key not in ["printing_mode", "machine_width", "machine_depth"]:
            return
        self._updateEnabled()

    def _onStackChanged(self):
        if self._global_container_stack:
            self._global_container_stack.propertyChanged.disconnect(self._onSettingPropertyChanged)
            extruders = ExtruderManager.getInstance().getActiveExtruderStacks()
            for extruder in extruders:
                extruder.propertyChanged.disconnect(self._onSettingPropertyChanged)

        self._global_container_stack = Application.getInstance().getGlobalContainerStack()

        if self._global_container_stack:
            self._global_container_stack.propertyChanged.connect(self._onSettingPropertyChanged)
            extruders = ExtruderManager.getInstance().getActiveExtruderStacks()
            for extruder in extruders:
                extruder.propertyChanged.connect(self._onSettingPropertyChanged)

    def _onSelectionChanged(self):
        # When selection is passed from one object to another object, first the selection is cleared
        # and then it is set to the new object. We are only interested in the change from no selection
        # to a selection or vice-versa, not in a change from one object to another. A timer is used to
        # "merge" a possible clear/select action in a single frame
        if Selection.hasSelection() != self._had_selection:
            self._had_selection_timer.start()

    def _selectionChangeDelay(self):
        has_selection = Selection.hasSelection()
        if not has_selection and self._had_selection:
            self._skip_press = True
        else:
            self._skip_press = False

        self._had_selection = has_selection

    def _createPlane(self, size):
        mesh = MeshBuilder()
        s = size / 2
        verts = [# 1 face with 4 corners
            [-s, 0, -s], [s, 0, -s], [s, 0, s], [-s, 0, s],
        ]
        mesh.setVertices(numpy.asarray(verts, dtype=numpy.float32))

        indices = []
        for i in range(0, 4, 4):  # All 1 quad (2 triangles)
            indices.append([i, i + 2, i + 1])
            indices.append([i, i + 3, i + 2])
        mesh.setIndices(numpy.asarray(indices, dtype=numpy.int32))

        mesh.calculateNormals()
        return mesh