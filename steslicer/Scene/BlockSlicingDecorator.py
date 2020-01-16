

from UM.Scene.SceneNodeDecorator import SceneNodeDecorator


class BlockSlicingDecorator(SceneNodeDecorator):
    def __init__(self) -> None:
        super().__init__()

    def isBlockSlicing(self) -> bool:
        return True
