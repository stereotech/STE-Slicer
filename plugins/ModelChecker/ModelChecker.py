# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import os

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, pyqtProperty

from UM.Application import Application
from UM.Extension import Extension
from UM.Logger import Logger
from UM.Message import Message
from UM.i18n import i18nCatalog
from UM.PluginRegistry import PluginRegistry
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

catalog = i18nCatalog("cura")


class ModelChecker(QObject, Extension):
    ##  Signal that gets emitted when anything changed that we need to check.
    onChanged = pyqtSignal()

    def __init__(self):
        super().__init__()

        self._button_view = None

        self._caution_message = Message("", #Message text gets set when the message gets shown, to display the models in question.
            lifetime = 0,
            title = catalog.i18nc("@info:title", "3D Model Assistant"))

        Application.getInstance().initializationFinished.connect(self._pluginsInitialized)
        Application.getInstance().getController().getScene().sceneChanged.connect(self._onChanged)
        Application.getInstance().globalContainerStackChanged.connect(self._onChanged)

    ##  Pass-through to allow UM.Signal to connect with a pyqtSignal.
    def _onChanged(self, *args, **kwargs):
        self.onChanged.emit()

    ##  Called when plug-ins are initialized.
    #
    #   This makes sure that we listen to changes of the material and that the
    #   button is created that indicates warnings with the current set-up.
    def _pluginsInitialized(self):
        Application.getInstance().getMachineManager().rootMaterialChanged.connect(self.onChanged)
        self._createView()

    def checkObjectsForShrinkage(self):
        shrinkage_threshold = 0.5 #From what shrinkage percentage a warning will be issued about the model size.
        warning_size_xy = 150 #The horizontal size of a model that would be too large when dealing with shrinking materials.
        warning_size_z = 100 #The vertical size of a model that would be too large when dealing with shrinking materials.

        # This function can be triggered in the middle of a machine change, so do not proceed if the machine change
        # has not done yet.
        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if global_container_stack is None:
            return False

        material_shrinkage = self._getMaterialShrinkage()

        warning_nodes = []

        # Check node material shrinkage and bounding box size
        for node in self.sliceableNodes():
            node_extruder_position = node.callDecoration("getActiveExtruderPosition")

            # This function can be triggered in the middle of a machine change, so do not proceed if the machine change
            # has not done yet.
            if str(node_extruder_position) not in global_container_stack.extruders:
                Application.getInstance().callLater(lambda: self.onChanged.emit())
                return False

            if material_shrinkage[node_extruder_position] > shrinkage_threshold:
                bbox = node.getBoundingBox()
                if bbox.width >= warning_size_xy or bbox.depth >= warning_size_xy or bbox.height >= warning_size_z:
                    warning_nodes.append(node)

        self._caution_message.setText(catalog.i18nc(
            "@info:status",
            "<p>One or more 3D models may not print optimally due to the model size and material configuration:</p>\n"
            "<p>{model_names}</p>\n"
            "<p>Find out how to ensure the best possible print quality and reliability.</p>\n"
            "<p><a href=\"https://ultimaker.com/3D-model-assistant\">View print quality guide</a></p>"
            ).format(model_names = ", ".join([n.getName() for n in warning_nodes])))

        return len(warning_nodes) > 0

    def sliceableNodes(self):
        # Add all sliceable scene nodes to check
        scene = Application.getInstance().getController().getScene()
        for node in DepthFirstIterator(scene.getRoot()):
            if node.callDecoration("isSliceable"):
                yield node

    ##  Creates the view used by show popup. The view is saved because of the fairly aggressive garbage collection.
    def _createView(self):
        Logger.log("d", "Creating model checker view.")

        # Create the plugin dialog component
        path = os.path.join(PluginRegistry.getInstance().getPluginPath("ModelChecker"), "ModelChecker.qml")
        self._button_view = Application.getInstance().createQmlComponent(path, {"manager": self})

        # The qml is only the button
        Application.getInstance().addAdditionalComponent("jobSpecsButton", self._button_view)

        Logger.log("d", "Model checker view created.")

    @pyqtProperty(bool, notify = onChanged)
    def hasWarnings(self):
        danger_shrinkage = self.checkObjectsForShrinkage()
        return any((danger_shrinkage, )) #If any of the checks fail, show the warning button.

    @pyqtSlot()
    def showWarnings(self):
        self._caution_message.show()

    def _getMaterialShrinkage(self):
        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if global_container_stack is None:
            return {}

        material_shrinkage = {}
        # Get all shrinkage values of materials used
        for extruder_position, extruder in global_container_stack.extruders.items():
            shrinkage = extruder.material.getProperty("material_shrinkage_percentage", "value")
            if shrinkage is None:
                shrinkage = 0
            material_shrinkage[extruder_position] = shrinkage
        return material_shrinkage
