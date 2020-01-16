

from . import FlavorParser

# This parser is intented for interpret the Marlin/Sprinter Firmware flavor
class MarlinFlavorParser(FlavorParser.FlavorParser):

    def __init__(self):
        super().__init__()