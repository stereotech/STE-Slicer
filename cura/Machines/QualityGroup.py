# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from typing import Dict, Optional, List, Set

from PyQt5.QtCore import QObject, pyqtSlot
from cura.Machines.ContainerNode import ContainerNode


#
# A QualityGroup represents a group of containers that must be applied to each ContainerStack when it's used.
# Some concrete examples are Quality and QualityChanges: when we select quality type "normal", this quality type
# must be applied to all stacks in a machine, although each stack can have different containers. Use an Ultimaker 3
# as an example, suppose we choose quality type "normal", the actual InstanceContainers on each stack may look
# as below:
#                       GlobalStack         ExtruderStack 1         ExtruderStack 2
# quality container:    um3_global_normal   um3_aa04_pla_normal     um3_aa04_abs_normal
#
# This QualityGroup is mainly used in quality and quality_changes to group the containers that can be applied to
# a machine, so when a quality/custom quality is selected, the container can be directly applied to each stack instead
# of looking them up again.
#
class QualityGroup(QObject):

    def __init__(self, name: str, quality_type: str, parent = None) -> None:
        super().__init__(parent)
        self.name = name
        self.node_for_global = None  # type: Optional[ContainerNode]
        self.nodes_for_extruders = {}  # type: Dict[int, ContainerNode]
        self.quality_type = quality_type
        self.is_available = False

    @pyqtSlot(result = str)
    def getName(self) -> str:
        return self.name

    def getAllKeys(self) -> Set[str]:
        result = set()  # type: Set[str]
        for node in [self.node_for_global] + list(self.nodes_for_extruders.values()):
            if node is None:
                continue
            container = node.getContainer()
            if container:
                result.update(container.getAllKeys())
        return result

    def getAllNodes(self) -> List[ContainerNode]:
        result = []
        if self.node_for_global is not None:
            result.append(self.node_for_global)
        for extruder_node in self.nodes_for_extruders.values():
            result.append(extruder_node)
        return result
