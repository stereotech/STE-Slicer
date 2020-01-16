
import os.path
from UM.Application import Application
from UM.Resources import Resources
from steslicer.Stages.SteSlicerStage import SteSlicerStage


##  Stage for preparing model (slicing).
class PrepareStage(SteSlicerStage):

    def __init__(self, parent = None):
        super().__init__(parent)
        Application.getInstance().engineCreatedSignal.connect(self._engineCreated)

    def _engineCreated(self):
        sidebar_component_path = os.path.join(Resources.getPath(Application.getInstance().ResourceTypes.QmlFiles),
                                              "PrepareSidebar.qml")
        self.addDisplayComponent("sidebar", sidebar_component_path)
