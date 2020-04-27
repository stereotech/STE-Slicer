import gc
import subprocess
from time import time

from UM.Application import Application
from UM.Job import Job
from UM.Logger import Logger
from UM.Message import Message
from UM.Signal import Signal
from UM.i18n import i18nCatalog

from .CliParser import CliParser

catalog = i18nCatalog("steslicer")


class ProcessCliJob(Job):
    processingProgress = Signal()
    timeMaterialEstimates = Signal()

    def __init__(self, process, output_path):
        super().__init__()
        self._parser = None
        self._output_path = output_path
        self._process = process #type: subprocess.Popen
        self._abort_requested = False
        self._build_plate_number = None

        self._gcode_list = []
        self._layers_data = []
        self._material_amounts = []
        self._times = {}

    def abort(self):
        self._abort_requested = True
        if self._parser:
            self._parser.cancel()
            self._parser = None

    def isCancelled(self) -> bool:
        return self._abort_requested

    def setBuildPlate(self, new_value):
        self._build_plate_number = new_value

    def getBuildPlate(self):
        return self._build_plate_number

    def getGCodeList(self):
        return self._gcode_list

    def getLayersData(self):
        return self._layers_data

    def getMaterialAmounts(self):
        return self._material_amounts

    def getTimes(self):
        return self._times

    def run(self):
        while self._process.poll() is None:
            Job.yieldThread()

        self.processingProgress.emit(0.3)
        Logger.log("d", "Glicer finished")

        gc.collect()

        with open(self._output_path, "r", encoding="utf-8") as file:
            file_data = file.read()
        self._parser = CliParser(self.getBuildPlate())
        self._parser.progressChanged.connect(self._onCliParserProgress)
        self._gcode_list = self._parser.processCliStream(file_data)
        if not self._abort_requested:
            self._layers_data = self._parser.getLayersData().values()
            self._material_amounts = self._parser.getMaterialAmounts()
            self._times = self._parser.getTimes()
            self._parser.progressChanged.disconnectAll()
        self._parser = None

    def _onCliParserProgress(self, amount):
        self.processingProgress.emit((amount / 100) * 0.7 + 0.3)

    def _onTimeMaterialEstimates(self, material_amounts, times):
        self.timeMaterialEstimates.emit(material_amounts, times)
