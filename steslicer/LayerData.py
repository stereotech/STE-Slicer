
from UM.Mesh.MeshData import MeshData


##  Class to holds the layer mesh and information about the layers.
# Immutable, use LayerDataBuilder to create one of these.
class LayerData(MeshData):
    def __init__(self, vertices = None, normals = None, indices = None, colors = None, uvs = None, file_name = None,
                 center_position = None, layers=None, element_counts=None, attributes=None):
        super().__init__(vertices=vertices, normals=normals, indices=indices, colors=colors, uvs=uvs,
                         file_name=file_name, center_position=center_position, attributes=attributes)
        self._layers = layers
        self._element_counts = element_counts

    def getLayer(self, layer):
        if layer in self._layers:
            return self._layers[layer]
        else:
            return None

    def getLayers(self):
        return self._layers

    def getElementCounts(self):
        return self._element_counts
