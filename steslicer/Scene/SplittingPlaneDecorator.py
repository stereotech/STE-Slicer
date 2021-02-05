from UM.Scene.SceneNodeDecorator import SceneNodeDecorator


class SplittingPlaneDecorator(SceneNodeDecorator):
    def __init__(self) -> None:
        super().__init__()

    def isSplittingPlane(self) -> bool:
        return True

    def __deepcopy__(self, memo) -> "SplittingPlaneDecorator":
        return type(self)()
