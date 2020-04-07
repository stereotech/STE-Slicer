from typing import TYPE_CHECKING, Optional, List, Set, Dict

from UM.Application import Application
from UM.Backend.Backend import Backend
from UM.PluginRegistry import PluginRegistry
from UM.Settings.ContainerRegistry import ContainerRegistry
from UM.Settings.SettingInstance import SettingInstance
from UM.Signal import Signal

backend_types = ["classic", "cylindrical"]

class BackendAlreadyAdded(Exception):
    pass

class BackendManager:
    __instance = None #type: BackendManager
    currendBackendChanged = Signal()

    printDurationMessage = Signal()

    def __init__(self, application) -> None:
        if BackendManager.__instance is not None:
            raise RuntimeError("Try to create singleton '%s' more than once" % self.__class__.__name__)
        BackendManager.__instance = self
        self._application = application  # type: Application
        self._container_registry = self._application.getContainerRegistry()
        self._global_container_stack = None
        self._backends_by_id = {} # type: Dict[str, Backend]
        self._backends_by_type = {} # type: Dict[str, Backend]
        self._backends_id_to_type_map = {} # type: Dict[str, str]
        self._current_backend = None # type: Optional[Backend]
        self._application.globalContainerStackChanged.connect(self._onGlobalContainerStackChanged)

    def _onGlobalContainerStackChanged(self):
        self._global_container_stack = self._application.getGlobalContainerStack()
        self._global_container_stack.propertyChanged.connect(
            self._onSettingChanged)
        printing_mode = self._global_container_stack.getProperty("printing_mode", "value")
        if printing_mode in backend_types:
            self._current_backend = self.getBackendByType(printing_mode)

    def initialize(self):
        PluginRegistry.addType("backend", self.addBackendEngine)

    def _onPrintDurationMessage(self, start_slice_job_build_plate, times, material_amounts):
        self.printDurationMessage.emit(start_slice_job_build_plate, times, material_amounts)

    def addBackendEngine(self, backend: "Backend") -> None:
        if backend.getPluginId() not in self._backends_by_id:
            self._backends_by_id[backend.getPluginId()] = backend
            backend.printDurationMessage.connect(self._onPrintDurationMessage)
            metadata = PluginRegistry.getInstance().getMetaData(backend.getPluginId())
            backend_type = metadata["backend_engine"].get("type", "")
            if backend_type in backend_types:
                self._backends_by_type[backend_type] = backend
                self._backends_id_to_type_map[backend.getPluginId()] = backend_type
            if self._current_backend is None:
                self._current_backend = self._backends_by_id[backend.getPluginId()]
                self.currendBackendChanged.emit()
        else:
            raise BackendAlreadyAdded("Backend with id %s was already added. Backends must have unique ids.", backend.getPluginId())

    def getBackends(self) -> Dict[str, "Backend"]:
        return self._backends_by_id

    def getBackendById(self, key: str) -> Optional["Backend"]:
        if key in self._backends_by_id:
            return self._backends_by_id[key]
        else:
            return None

    def getBackendByType(self, backend_type: str) -> Optional["Backend"]:
        if backend_type in self._backends_by_type:
            return self._backends_by_type[backend_type]
        else:
            return None

    def getCurrentBackend(self) -> Optional[Backend]:
        return self._current_backend

    def _onSettingChanged(self,  setting_key: str, property_name: str) -> None:
        if property_name == "value" and setting_key == "printing_mode":
            value = self._global_container_stack.getProperty(setting_key, property_name)
            if value is not None:
                current_type = self._backends_id_to_type_map[self._current_backend.getPluginId()]
                if current_type != value and value in backend_types:
                    new_backend = self.getBackendByType(value)
                    if new_backend is not None:
                        self._current_backend = new_backend
                        self.currendBackendChanged.emit()