from UM.Mesh.MeshWriter import MeshWriter
from UM.Logger import Logger

from cura.CuraApplication import CuraApplication

import time
import struct

from csg.core import CSG, Polygon, BSPNode, Vertex

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")


class GlicerWriter(MeshWriter):
    def write(self, stream, nodes, mode=MeshWriter.OutputMode.BinaryMode):
        radius = CuraApplication.getInstance().getGlobalContainerStack(
        ).getProperty("cylindrical_mode_base_diameter", "value") / 2
        height = CuraApplication.getInstance().getGlobalContainerStack(
        ).getProperty("machine_height", "value")
        # try:
        MeshWriter._meshNodes(nodes).__next__()
        for node in nodes:
            mesh_data = node.getMeshData().getTransformed(node.getWorldTransformation())
            verts = mesh_data.getVertices()
            if verts is None:
                continue
            faces = None
            if mesh_data.hasIndices():
                faces = mesh_data.getIndices()
            else:
                faces = mesh_data.getVertexCount()
            if faces is None:
                continue
            cutting_cylinder = CSG.cylinder()
            polygons = []
            for face in faces:
                v1 = Vertex(verts[face[0]])
                v2 = Vertex(verts[face[1]])
                v3 = Vertex(verts[face[2]])
                polygon = Polygon([[v1[0], -v1[2], v1[1]],
                                   [v2[0], -v2[2], v2[1]],
                                   [v3[0], -v3[2], v3[1]], ])
                polygons.append(polygon)
            node = BSPNode(polygons)
            target = CSG.fromPolygons(node)
            result = target.subtract(cutting_cylinder)
            result.saveVTK("test.vtk")
            return True
        # except:
        #    Logger.log("e", "There is no mesh to write.")
        #    self.setInformation(catalog.i18nc(
        #        "@error:no mesh", "There is no mesh to write."))
        #    return False  # Don't try to write a file if there is no mesh.
