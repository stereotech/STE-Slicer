import numpy as np
from UM.Mesh.MeshData import MeshData

from trimesh.base import Trimesh
from trimesh.creation import triangulate_polygon
from trimesh import util
from trimesh import intersections
from trimesh import geometry
from trimesh import grouping
from trimesh import transformations as tf

from trimesh.constants import log, tol
from trimesh.triangles import windings_aligned

def SplitByPlane(mesh,
                plane_normal,
                plane_origin,
                cap=False,
                cached_dots=None,
                 overlap=0,
                **kwargs):
    mesh1 = SplitByPlaneOneSide(mesh, plane_normal, plane_origin + (-plane_normal * overlap), cap, cached_dots, **kwargs)
    mesh2 = SplitByPlaneOneSide(mesh, -plane_normal, plane_origin, cap, cached_dots, True, **kwargs)
    return mesh1, mesh2

def SplitByPlaneOneSide(mesh,
                plane_normal,
                plane_origin,
                cap=False,
                cached_dots=None,
                reversed=False,
                **kwargs):
    """
    Slice a mesh with a plane, returning a new mesh that is the
    portion of the original mesh to the positive normal side of the plane
    Parameters
    ---------
    mesh : Trimesh object
      Source mesh to slice
    plane_normal : (3,) float
      Normal vector of plane to intersect with mesh
    plane_origin :  (3,) float
      Point on plane to intersect with mesh
    cap : bool
      If True, cap the result with a triangulated polygon
    cached_dots : (n, 3) float
      If an external function has stored dot
      products pass them here to avoid recomputing
    kwargs : dict
      Passed to the newly created sliced mesh
    Returns
    ----------
    new_vertices : (n, 3) float
        Vertices of sliced mesh
    new_faces : (n, 3) int
        Faces of sliced mesh
    """
    # check input for none
    if mesh is None:
        return None

    # check input plane
    plane_normal = np.asanyarray(plane_normal,
                                 dtype=np.float64)
    plane_origin = np.asanyarray(plane_origin,
                                 dtype=np.float64)

    # check to make sure origins and normals have acceptable shape
    shape_ok = ((plane_origin.shape == (3,) or
                 util.is_shape(plane_origin, (-1, 3))) and
                (plane_normal.shape == (3,) or
                 util.is_shape(plane_normal, (-1, 3))) and
                plane_origin.shape == plane_normal.shape)
    if not shape_ok:
        raise ValueError('plane origins and normals must be (n, 3)!')

    # start with copy of original mesh, faces, and vertices
    sliced_mesh = mesh.copy()
    vertices = mesh.vertices.copy()
    faces = mesh.faces.copy()

    # slice away specified planes
    for origin, normal in zip(plane_origin.reshape((-1, 3)),
                              plane_normal.reshape((-1, 3))):

        # calculate dots here if not passed in to save time
        # in case of cap
        if cached_dots is None:
            # dot product of each vertex with the plane normal indexed by face
            # so for each face the dot product of each vertex is a row
            # shape is the same as faces (n,3)
            dots = np.einsum('i,ij->j', normal,
                             (vertices - origin).T)[faces]
        else:
            dots = cached_dots
        # save the new vertices and faces
        vertices, faces = intersections.slice_faces_plane(vertices=vertices,
                                            faces=faces,
                                            plane_normal=normal,
                                            plane_origin=origin,
                                            cached_dots=dots)

        # check if cap arg specified
        if cap:
            # check if mesh is watertight (can't cap if not)
            if not sliced_mesh.is_watertight:
                raise ValueError('Input mesh must be watertight to cap slice')
            path = sliced_mesh.section(plane_normal=normal,
                                       plane_origin=origin)
            if not path:
                if reversed:
                    return sliced_mesh
                else:
                    return None
            # transform Path3D onto XY plane for triangulation
            on_plane, to_3D = path.to_planar()

            # triangulate each closed region of 2D cap
            # without adding any new vertices
            v, f = [], []
            for polygon in on_plane.polygons_full:
                t = triangulate_polygon(
                    polygon, triangle_args='pY', engine='triangle')
                v.append(t[0])
                f.append(t[1])

                if tol.strict:
                    # in unit tests make sure that our triangulation didn't
                    # insert any new vertices which would break watertightness
                    from scipy.spatial import cKDTree
                    # get all interior and exterior points on tree
                    check = [np.array(polygon.exterior.coords)]
                    check.extend(np.array(i.coords) for i in polygon.interiors)
                    tree = cKDTree(np.vstack(check))
                    # every new vertex should be on an old vertex
                    assert np.allclose(tree.query(v[-1])[0], 0.0)

            # append regions and reindex
            vf, ff = util.append_faces(v, f)

            # make vertices 3D and transform back to mesh frame
            vf = tf.transform_points(
                np.column_stack((vf, np.zeros(len(vf)))),
                to_3D)

            # check to see if our new faces are aligned with our normal
            #check = windings_aligned(vf[ff], normal)
#
            ## if 50% of our new faces are aligned with the normal flip
            #if check.astype(np.float64).mean() > 0.5:
            #    ff = np.fliplr(ff)

            # add cap vertices and faces and reindex
            vertices, faces = util.append_faces([vertices, vf], [faces, ff])

            # Update mesh with cap (processing needed to merge vertices)
            sliced_mesh = Trimesh(vertices=vertices, faces=faces)
            vertices, faces = sliced_mesh.vertices.copy(), sliced_mesh.faces.copy()

    return sliced_mesh

