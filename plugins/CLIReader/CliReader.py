from UM.FileHandler.FileReader import FileReader
from UM.Mesh.MeshReader import MeshReader
from UM.i18n import i18nCatalog
from UM.Application import Application
from UM.MimeTypeDatabase import MimeTypeDatabase, MimeType
from . import CliParser

catalog = i18nCatalog("steslicer")


class CliReader(MeshReader):
    def __init__(self):
        super().__init__()
        MimeTypeDatabase.addMimeType(
            MimeType(
                name="application/x-ste-cli-file",
                comment="STE Slicer Cli file",
                suffixes=["cli"]
            )
        )
        self._supported_extensions = [".cli"]

    def _read(self, file_name):
        with open(file_name, "r", encoding="utf-8") as file:
            file_data = file.read()
        return self.readFromStream(file_data)

    def readFromStream(self, stream):
        parser = CliParser.CliParser()
        return parser.processCliStream(stream)
