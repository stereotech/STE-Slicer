import os.path
from UM.Application import Application
from UM.PluginRegistry import PluginRegistry
from UM.Resources import Resources
from steslicer.Stages.SteSlicerStage import SteSlicerStage


class STEAppStage(SteSlicerStage):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Wait until QML engine is created, otherwise creating the new QML components will fail
        Application.getInstance().engineCreatedSignal.connect(self._onEngineCreated)
        self._printer_output_device = None

        self._active_print_job = None
        self._active_printer = None


    def _setActivePrintJob(self, print_job):
        if self._active_print_job != print_job:
            self._active_print_job = print_job

    def _setActivePrinter(self, printer):
        if self._active_printer != printer:
            if self._active_printer:
                self._active_printer.activePrintJobChanged.disconnect(
                    self._onActivePrintJobChanged)
            self._active_printer = printer
            if self._active_printer:
                self._setActivePrintJob(self._active_printer.activePrintJob)
                # Jobs might change, so we need to listen to it's changes.
                self._active_printer.activePrintJobChanged.connect(
                    self._onActivePrintJobChanged)
            else:
                self._setActivePrintJob(None)

    def _onActivePrintJobChanged(self):
        self._setActivePrintJob(self._active_printer.activePrintJob)

    def _onActivePrinterChanged(self):
        self._setActivePrinter(self._printer_output_device.activePrinter)

    def _onOutputDevicesChanged(self):
        try:
            # We assume that you are monitoring the device with the highest priority.
            new_output_device = Application.getInstance(
            ).getMachineManager().printerOutputDevices[0]
            if new_output_device != self._printer_output_device:
                if self._printer_output_device:
                    try:
                        self._printer_output_device.printersChanged.disconnect(
                            self._onActivePrinterChanged)
                    except TypeError:
                        # Ignore stupid "Not connected" errors.
                        pass

                self._printer_output_device = new_output_device

                self._printer_output_device.printersChanged.connect(
                    self._onActivePrinterChanged)
                self._setActivePrinter(
                    self._printer_output_device.activePrinter)
        except IndexError:
            pass

    def _onEngineCreated(self):
        # We can only connect now, as we need to be sure that everything is loaded (plugins get created quite early)
        Application.getInstance().getMachineManager(
        ).outputDevicesChanged.connect(self._onOutputDevicesChanged)
        self._onOutputDevicesChanged()
        self._updateMainOverlay()
        self._updateSidebar()
        icon_path = os.path.join(PluginRegistry.getInstance().getPluginPath("STEAppStage"),
                                           "steapp.svg")
        self.setIconSource(icon_path)

    def _updateMainOverlay(self):
        main_component_path = os.path.join(PluginRegistry.getInstance().getPluginPath("STEAppStage"),
                                           "MonitorMainView.qml")
        self.addDisplayComponent("main", main_component_path)

    def _updateSidebar(self):
        sidebar_component_path = os.path.join(Resources.getPath(Application.getInstance().ResourceTypes.QmlFiles),
                                              "MonitorSidebar.qml")
        self.addDisplayComponent("sidebar", sidebar_component_path)
