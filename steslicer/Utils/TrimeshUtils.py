import numpy as np
from trimesh import transformations as tf
from trimesh import triangles
from trimesh.constants import log, tol
from trimesh.base import Trimesh

def revolve(linestring,
            angle=None,
            sections=None,
            transform=None,
            **kwargs):
    """
    Revolve a 2D line string around the 2D Y axis, with a result with
    the 2D Y axis pointing along the 3D Z axis.
    This function is intended to handle the complexity of indexing
    and is intended to be used to create all radially symmetric primitives,
    eventually including cylinders, annular cylinders, capsules, cones,
    and UV spheres.
    Note that if your linestring is closed, it needs to be counterclockwise
    if you would like face winding and normals facing outwards.
    Parameters
    -------------
    linestring : (n, 2) float
      Lines in 2D which will be revolved
    angle : None or float
      Angle in radians to revolve curve by
    sections : None or int
      Number of sections result should have
      If not specified default is 32 per revolution
    transform : None or (4, 4) float
      Transform to apply to mesh after construction
    **kwargs : dict
      Passed to Trimesh constructor
    Returns
    --------------
    revolved : Trimesh
      Mesh representing revolved result
    """
    linestring = np.asanyarray(linestring, dtype=np.float64)

    # linestring must be ordered 2D points
    if len(linestring.shape) != 2 or linestring.shape[1] != 2:
        raise ValueError('linestring must be 2D!')

    if angle is None:
        # default to closing the revolution
        angle = np.pi * 2
        closed = True
    else:
        # check passed angle value
        closed = angle >= ((np.pi * 2) - 1e-8)

    if sections is None:
        # default to 32 sections for a full revolution
        sections = int(angle / (np.pi * 2) * 32)
    # change to face count
    sections += 1
    # create equally spaced angles
    theta = np.linspace(0, angle, sections)

    # 2D points around the revolution
    points = np.column_stack((np.cos(theta), np.sin(theta)))

    # how many points per slice
    per = len(linestring)
    # use the 2D X component as radius
    radius = linestring[:, 0]
    # use the 2D Y component as the height along revolution
    height = linestring[:, 1]
    # a lot of tiling to get our 3D vertices
    vertices = np.column_stack((
        np.tile(points, (1, per)).reshape((-1, 2)) *
        np.tile(radius, len(points)).reshape((-1, 1)),
        np.tile(height, len(points))))

    if closed:
        # should be a duplicate set of vertices
        assert np.allclose(vertices[:per],
                           vertices[-per:])
        # chop off duplicate vertices
        vertices = vertices[:-per]

    if transform is not None:
        # apply transform to vertices
        vertices = tf.transform_points(vertices, transform)

    # how many slices of the pie
    slices = len(theta) - 1

    # start with a quad for every segment
    # this is a superset which will then be reduced
    quad = np.array([0, per, 1,
                     1, per, per + 1])
    # stack the faces for a single slice of the revolution
    single = np.tile(quad, per).reshape((-1, 3))
    # `per` is basically the stride of the vertices
    single += np.tile(np.arange(per), (2, 1)).T.reshape((-1, 1))
    # remove any zero-area triangle
    # this covers many cases without having to think too much
    single = single[triangles.area(vertices[single]) > tol.merge]

    # how much to offset each slice
    # note arange multiplied by vertex stride
    # but tiled by the number of faces we actually have
    offset = np.tile(np.arange(slices) * per,
                     (len(single), 1)).T.reshape((-1, 1))
    # stack a single slice into N slices
    stacked = np.tile(single.ravel(), slices).reshape((-1, 3))

    if tol.strict:
        # make sure we didn't screw up stacking operation
        assert np.allclose(stacked.reshape((-1, single.shape[0], 3)) - single, 0)

    # offset stacked and wrap vertices
    faces = (stacked + offset) % len(vertices)

    # create the mesh from our vertices and faces
    mesh = Trimesh(vertices=vertices, faces=faces,
                   **kwargs)

    # strict checks run only in unit tests
    if (tol.strict and
            (np.allclose(radius[[0, -1]], 0.0) or
             np.allclose(linestring[0], linestring[-1]))):
        # if revolved curve starts and ends with zero radius
        # it should really be a valid volume, unless the sign
        # reversed on the input linestring
        assert mesh.is_volume

    return