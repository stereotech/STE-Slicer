# Copyright (c) 2015 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from UM.Operations.Operation import Operation
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Scene.SceneNode import SceneNode

##  A specialised operation designed specifically to modify the previous operation.
class PlatformPhysicsOperation(Operation):
    def __init__(self, node, translation):
        super().__init__()
        self._node = node
        self._old_transformation = node.getLocalTransformation()
        self._translation = translation
        self._always_merge = True

    def undo(self):
        self._node.setTransformation(self._old_transformation)

    def redo(self):
        self._node.translate(self._translation, SceneNode.TransformSpace.World)

    def mergeWith(self, other):
        group = GroupedOperation()

        group.addOperation(other)
        group.addOperation(self)

        return group

    def __repr__(self):
        return "PlatformPhysicsOperation(translation = {0})".format(self._translation)
