

from enum import Enum


class VariantType(Enum):
    BUILD_PLATE = "buildplate"
    NOZZLE = "nozzle"


ALL_VARIANT_TYPES = (VariantType.BUILD_PLATE, VariantType.NOZZLE)


__all__ = ["VariantType", "ALL_VARIANT_TYPES"]
