from UM.Scene.SceneNodeDecorator import SceneNodeDecorator
from steslicer.Scene.SteSlicerSceneNode import SteSlicerSceneNode


##  Make a SceneNode build plate aware SteSlicerSceneNode objects all have this decorator.
class BuildPlateDecorator(SceneNodeDecorator):
    def __init__(self, build_plate_number = -1):
        super().__init__()
        self._build_plate_number = None
        self.setBuildPlateNumber(build_plate_number)

    def setBuildPlateNumber(self, nr):
        # Make sure that groups are set correctly
        # setBuildPlateForSelection in SteSlicerActions makes sure that no single childs are set.
        self._build_plate_number = nr
        if isinstance(self._node, SteSlicerSceneNode):
            self._node.transformChanged()  # trigger refresh node without introducing a new signal
        if self._node:
            for child in self._node.getChildren():
                child.callDecoration("setBuildPlateNumber", nr)

    def getBuildPlateNumber(self):
        return self._build_plate_number

    def __deepcopy__(self, memo):
        return BuildPlateDecorator()
