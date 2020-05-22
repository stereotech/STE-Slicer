import numpy
from UM.Mesh.MeshWriter import MeshWriter
from UM.Logger import Logger

from steslicer.SteSlicerApplication import SteSlicerApplication

import time
import struct

import numpy as np
import trimesh
import trimesh.primitives

from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")


class GlicerWriter(MeshWriter):
    def write(self, stream, nodes, mode=MeshWriter.OutputMode.BinaryMode):
        radius = SteSlicerApplication.getInstance().getGlobalContainerStack(
        ).getProperty("cylindrical_mode_base_diameter", "value") / 2
        height = SteSlicerApplication.getInstance().getGlobalContainerStack(
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
                num_verts = mesh_data.getVertexCount()
                faces = numpy.empty((int(num_verts / 3 + 1), 3), numpy.int32)
                for i in range(0, num_verts - 2, 3):
                    faces[int(i / 3):] = [i, i + 1, i + 2]
            if faces is None:
                continue
            vertices = []
            for vert in verts:
                vertices.append([vert[0], -vert[2], vert[1]])
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            cutting_cylinder = trimesh.primitives.Cylinder(
                radius=radius, height=height)
            result = mesh.difference(cutting_cylinder, engine="scad")
            stream.write("Uranium STLWriter {0}".format(time.strftime(
                "%a %d %b %Y %H:%M:%S")).encode().ljust(80, b"\000"))
            face_count = len(result.faces)
            # Write number of faces to STL
            stream.write(struct.pack("<I", int(face_count)))
            verts = result.vertices
            for face in result.faces:
                v1 = verts[face[0]]
                v2 = verts[face[1]]
                v3 = verts[face[2]]
                stream.write(struct.pack("<fff", 0.0, 0.0, 0.0))
                stream.write(struct.pack("<fff", v1[0], v1[1], v1[2]))
                stream.write(struct.pack("<fff", v2[0], v2[1], v2[2]))
                stream.write(struct.pack("<fff", v3[0], v3[1], v3[2]))
                stream.write(struct.pack("<H", 0))
            return True
        # except:
        #    Logger.log("e", "There is no mesh to write.")
        #    self.setInformation(catalog.i18nc(
        #        "@error:no mesh", "There is no mesh to write."))
        #    return False  # Don't try to write a file if there is no mesh.
