from UM.Settings.ContainerRegistry import ContainerRegistry

from steslicer.SteSlicerApplication import SteSlicerApplication


class BackendManager:
    __instance = None #type: BackendManager

    def __init__(self, application: "SteSlicerApplication") -> None:
        if BackendManager.__instance is not None:
            raise RuntimeError("Try to create singleton '%s' more than once" % self.__class__.__name__)
        BackendManager.__instance = self
        self._application = application  # type: SteSlicerApplication


