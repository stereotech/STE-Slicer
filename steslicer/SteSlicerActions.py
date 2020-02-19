

from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtGui import QDesktopServices
from typing import List, TYPE_CHECKING

from UM.Event import CallFunctionEvent
from UM.FlameProfiler import pyqtSlot
from UM.Math.Vector import Vector
from UM.Scene.Selection import Selection
from UM.Scene.Iterator.BreadthFirstIterator import BreadthFirstIterator
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from UM.Operations.TranslateOperation import TranslateOperation

import steslicer.SteSlicerApplication
from steslicer.Operations.SetParentOperation import SetParentOperation
from steslicer.MultiplyObjectsJob import MultiplyObjectsJob
from steslicer.Settings.SetObjectExtruderOperation import SetObjectExtruderOperation
from steslicer.Settings.ExtruderManager import ExtruderManager

from steslicer.Operations.SetBuildPlateNumberOperation import SetBuildPlateNumberOperation

from UM.Logger import Logger

if TYPE_CHECKING:
    from UM.Scene.SceneNode import SceneNode

class SteSlicerActions(QObject):
    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)

    @pyqtSlot()
    def showLicenseWindow(self) -> None:
        steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().getLicenseManager().showLicenseWindow()

    @pyqtSlot()
    def openDocumentation(self) -> None:
        # Starting a web browser from a signal handler connected to a menu will crash on windows.
        # So instead, defer the call to the next run of the event loop, since that does work.
        # Note that weirdly enough, only signal handlers that open a web browser fail like that.
        event = CallFunctionEvent(self._openUrl, [QUrl("https://stereotech.org/manuals/steslicer")], {})
        steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().functionEvent(event)

    @pyqtSlot()
    def openBugReportPage(self) -> None:
        event = CallFunctionEvent(self._openUrl, [QUrl("https://gitlab.com/stereotech/steslicer/ste-slicer/issues")], {})
        steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().functionEvent(event)

    ##  Reset camera position and direction to default
    @pyqtSlot()
    def homeCamera(self) -> None:
        scene = steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().getController().getScene()
        camera = scene.getActiveCamera()
        if camera:
            diagonal_size = steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().getBuildVolume().getDiagonalSize()
            camera.setPosition(Vector(-80, 250, 700) * diagonal_size / 375)
            camera.setPerspective(True)
            camera.lookAt(Vector(0, 0, 0))

    ##  Center all objects in the selection
    @pyqtSlot()
    def centerSelection(self) -> None:
        operation = GroupedOperation()
        for node in Selection.getAllSelectedObjects():
            current_node = node
            while current_node.getParent() and current_node.getParent().callDecoration("isGroup"):
                current_node = current_node.getParent()

            #   This was formerly done with SetTransformOperation but because of
            #   unpredictable matrix deconstruction it was possible that mirrors
            #   could manifest as rotations. Centering is therefore done by
            #   moving the node to negative whatever its position is:
            center_operation = TranslateOperation(current_node, -current_node._position)
            operation.addOperation(center_operation)
        operation.push()

    ##  Multiply all objects in the selection
    #
    #   \param count The number of times to multiply the selection.
    @pyqtSlot(int)
    def multiplySelection(self, count: int) -> None:
        min_offset = steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().getBuildVolume().getEdgeDisallowedSize() + 2  # Allow for some rounding errors
        job = MultiplyObjectsJob(Selection.getAllSelectedObjects(), count, min_offset = max(min_offset, 8))
        job.start()

    ##  Delete all selected objects.
    @pyqtSlot()
    def deleteSelection(self) -> None:
        if not steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().getController().getToolsEnabled():
            return

        removed_group_nodes = [] #type: List[SceneNode]
        op = GroupedOperation()
        nodes = Selection.getAllSelectedObjects()
        for node in nodes:
            op.addOperation(RemoveSceneNodeOperation(node))
            group_node = node.getParent()
            if group_node and group_node.callDecoration("isGroup") and group_node not in removed_group_nodes:
                remaining_nodes_in_group = list(set(group_node.getChildren()) - set(nodes))
                if len(remaining_nodes_in_group) == 1:
                    removed_group_nodes.append(group_node)
                    op.addOperation(SetParentOperation(remaining_nodes_in_group[0], group_node.getParent()))
                    op.addOperation(RemoveSceneNodeOperation(group_node))

            # Reset the print information
            steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().getController().getScene().sceneChanged.emit(node)

        op.push()

    ##  Set the extruder that should be used to print the selection.
    #
    #   \param extruder_id The ID of the extruder stack to use for the selected objects.
    @pyqtSlot(str)
    def setExtruderForSelection(self, extruder_id: str) -> None:
        operation = GroupedOperation()

        nodes_to_change = []
        for node in Selection.getAllSelectedObjects():
            # If the node is a group, apply the active extruder to all children of the group.
            if node.callDecoration("isGroup"):
                for grouped_node in BreadthFirstIterator(node): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                    if grouped_node.callDecoration("getActiveExtruder") == extruder_id:
                        continue

                    if grouped_node.callDecoration("isGroup"):
                        continue

                    nodes_to_change.append(grouped_node)
                continue

            # Do not change any nodes that already have the right extruder set.
            if node.callDecoration("getActiveExtruder") == extruder_id:
                continue

            nodes_to_change.append(node)

        if not nodes_to_change:
            # If there are no changes to make, we still need to reset the selected extruders.
            # This is a workaround for checked menu items being deselected while still being
            # selected.
            ExtruderManager.getInstance().resetSelectedObjectExtruders()
            return

        for node in nodes_to_change:
            operation.addOperation(SetObjectExtruderOperation(node, extruder_id))
        operation.push()

    @pyqtSlot(int)
    def setBuildPlateForSelection(self, build_plate_nr: int) -> None:
        Logger.log("d", "Setting build plate number... %d" % build_plate_nr)
        operation = GroupedOperation()

        root = steslicer.SteSlicerApplication.SteSlicerApplication.getInstance().getController().getScene().getRoot()

        nodes_to_change = []
        for node in Selection.getAllSelectedObjects():
            parent_node = node  # Find the parent node to change instead
            while parent_node.getParent() != root:
                parent_node = parent_node.getParent()

            for single_node in BreadthFirstIterator(parent_node): #type: ignore #Ignore type error because iter() should get called automatically by Python syntax.
                nodes_to_change.append(single_node)

        if not nodes_to_change:
            Logger.log("d", "Nothing to change.")
            return

        for node in nodes_to_change:
            operation.addOperation(SetBuildPlateNumberOperation(node, build_plate_nr))
        operation.push()

        Selection.clear()

    def _openUrl(self, url: QUrl) -> None:
        QDesktopServices.openUrl(url)
