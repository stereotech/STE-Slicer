# Copyright (c) 2017 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

from UM.Application import Application
from typing import Any
import numpy


class LayerPolygon:
    NoneType = 0
    Inset0Type = 1
    InsetXType = 2
    SkinType = 3
    SupportType = 4
    SkirtType = 5
    InfillType = 6
    SupportInfillType = 7
    MoveCombingType = 8
    MoveRetractionType = 9
    SupportInterfaceType = 10
    __number_of_types = 11

    __jump_map = numpy.logical_or(numpy.logical_or(numpy.arange(__number_of_types) == NoneType, numpy.arange(__number_of_types) == MoveCombingType), numpy.arange(__number_of_types) == MoveRetractionType)

    ##  LayerPolygon, used in ProcessSlicedLayersJob
    #   \param extruder
    #   \param line_types array with line_types
    #   \param data new_points
    #   \param line_widths array with line widths
    #   \param line_thicknesses: array with type as index and thickness as value
    #   \param line_feedrates array with line feedrates
    def __init__(self, extruder, line_types, data, line_widths, line_thicknesses, line_feedrates):
        self._extruder = extruder
        self._types = line_types
        for i in range(len(self._types)):
            if self._types[i] >= self.__number_of_types: #Got faulty line data from the engine.
                self._types[i] = self.NoneType
        self._data = data
        self._line_widths = line_widths
        self._line_thicknesses = line_thicknesses
        self._line_feedrates = line_feedrates

        self._vertex_begin = 0
        self._vertex_end = 0
        self._index_begin = 0
        self._index_end = 0

        self._jump_mask = self.__jump_map[self._types]
        self._jump_count = numpy.sum(self._jump_mask)
        self._mesh_line_count = len(self._types) - self._jump_count
        self._vertex_count = self._mesh_line_count + numpy.sum(self._types[1:] == self._types[:-1])

        # Buffering the colors shouldn't be necessary as it is not 
        # re-used and can save alot of memory usage.
        self._color_map = LayerPolygon.getColorMap()
        self._colors = self._color_map[self._types]
        
        # When type is used as index returns true if type == LayerPolygon.InfillType or type == LayerPolygon.SkinType or type == LayerPolygon.SupportInfillType
        # Should be generated in better way, not hardcoded.
        self._isInfillOrSkinTypeMap = numpy.array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1], dtype=numpy.bool)
        
        self._build_cache_line_mesh_mask = None
        self._build_cache_needed_points = None
        
    def buildCache(self):
        # For the line mesh we do not draw Infill or Jumps. Therefore those lines are filtered out.
        self._build_cache_line_mesh_mask = numpy.ones(self._jump_mask.shape, dtype=bool)
        mesh_line_count = numpy.sum(self._build_cache_line_mesh_mask)
        self._index_begin = 0
        self._index_end = mesh_line_count
        
        self._build_cache_needed_points = numpy.ones((len(self._types), 2), dtype=numpy.bool)
        # Only if the type of line segment changes do we need to add an extra vertex to change colors
        self._build_cache_needed_points[1:, 0][:, numpy.newaxis] = self._types[1:] != self._types[:-1]
        # Mark points as unneeded if they are of types we don't want in the line mesh according to the calculated mask
        numpy.logical_and(self._build_cache_needed_points, self._build_cache_line_mesh_mask, self._build_cache_needed_points )

        self._vertex_begin = 0
        self._vertex_end = numpy.sum( self._build_cache_needed_points )

    ##  Set all the arrays provided by the function caller, representing the LayerPolygon
    #   The arrays are either by vertex or by indices.
    #
    #   \param vertex_offset : determines where to start and end filling the arrays
    #   \param index_offset : determines where to start and end filling the arrays
    #   \param vertices : vertex numpy array to be filled
    #   \param colors : vertex numpy array to be filled
    #   \param line_dimensions : vertex numpy array to be filled
    #   \param feedrates : vertex numpy array to be filled
    #   \param extruders : vertex numpy array to be filled
    #   \param line_types : vertex numpy array to be filled
    #   \param indices : index numpy array to be filled
    def build(self, vertex_offset, index_offset, vertices, colors, line_dimensions, feedrates, extruders, line_types, indices):
        if self._build_cache_line_mesh_mask is None or self._build_cache_needed_points is None:
            self.buildCache()
            
        line_mesh_mask = self._build_cache_line_mesh_mask
        needed_points_list = self._build_cache_needed_points
        
        # Index to the points we need to represent the line mesh. This is constructed by generating simple
        # start and end points for each line. For line segment n these are points n and n+1. Row n reads [n n+1] 
        # Then then the indices for the points we don't need are thrown away based on the pre-calculated list. 
        index_list = ( numpy.arange(len(self._types)).reshape((-1, 1)) + numpy.array([[0, 1]]) ).reshape((-1, 1))[needed_points_list.reshape((-1, 1))]
        
        # The relative values of begin and end indices have already been set in buildCache, so we only need to offset them to the parents offset.
        self._vertex_begin += vertex_offset
        self._vertex_end += vertex_offset
        
        # Points are picked based on the index list to get the vertices needed. 
        vertices[self._vertex_begin:self._vertex_end, :] = self._data[index_list, :]

        # Create an array with colors for each vertex and remove the color data for the points that has been thrown away. 
        colors[self._vertex_begin:self._vertex_end, :] = numpy.tile(self._colors, (1, 2)).reshape((-1, 4))[needed_points_list.ravel()]

        # Create an array with line widths and thicknesses for each vertex.
        line_dimensions[self._vertex_begin:self._vertex_end, 0] = numpy.tile(self._line_widths, (1, 2)).reshape((-1, 1))[needed_points_list.ravel()][:, 0]
        line_dimensions[self._vertex_begin:self._vertex_end, 1] = numpy.tile(self._line_thicknesses, (1, 2)).reshape((-1, 1))[needed_points_list.ravel()][:, 0]

        # Create an array with feedrates for each line
        feedrates[self._vertex_begin:self._vertex_end] = numpy.tile(self._line_feedrates, (1, 2)).reshape((-1, 1))[needed_points_list.ravel()][:, 0]

        extruders[self._vertex_begin:self._vertex_end] = self._extruder

        # Convert type per vertex to type per line
        line_types[self._vertex_begin:self._vertex_end] = numpy.tile(self._types, (1, 2)).reshape((-1, 1))[needed_points_list.ravel()][:, 0]

        # The relative values of begin and end indices have already been set in buildCache, so we only need to offset them to the parents offset.
        self._index_begin += index_offset
        self._index_end += index_offset
        
        indices[self._index_begin:self._index_end, :] = numpy.arange(self._index_end-self._index_begin, dtype=numpy.int32).reshape((-1, 1))
        # When the line type changes the index needs to be increased by 2.
        indices[self._index_begin:self._index_end, :] += numpy.cumsum(needed_points_list[line_mesh_mask.ravel(), 0], dtype=numpy.int32).reshape((-1, 1))
        # Each line segment goes from it's starting point p to p+1, offset by the vertex index. 
        # The -1 is to compensate for the neccecarily True value of needed_points_list[0,0] which causes an unwanted +1 in cumsum above.
        indices[self._index_begin:self._index_end, :] += numpy.array([self._vertex_begin - 1, self._vertex_begin])
        
        self._build_cache_line_mesh_mask = None
        self._build_cache_needed_points = None

    def getColors(self):
        return self._colors

    def mapLineTypeToColor(self, line_types):
        return self._color_map[line_types]

    def isInfillOrSkinType(self, line_types):
        return self._isInfillOrSkinTypeMap[line_types]

    def lineMeshVertexCount(self):
        return (self._vertex_end - self._vertex_begin)

    def lineMeshElementCount(self):
        return (self._index_end - self._index_begin)

    @property
    def extruder(self):
        return self._extruder

    @property
    def types(self):
        return self._types

    @property
    def data(self):
        return self._data

    @property
    def elementCount(self):
        return (self._index_end - self._index_begin) * 2  # The range of vertices multiplied by 2 since each vertex is used twice

    @property
    def lineWidths(self):
        return self._line_widths

    @property
    def lineThicknesses(self):
        return self._line_thicknesses

    @property
    def lineFeedrates(self):
        return self._line_feedrates
    
    @property
    def jumpMask(self):
        return self._jump_mask

    @property
    def meshLineCount(self):
        return self._mesh_line_count

    @property
    def jumpCount(self):
        return self._jump_count

    # Calculate normals for the entire polygon using numpy.
    def getNormals(self):
        normals = numpy.copy(self._data)
        normals[:, 1] = 0.0 # We are only interested in 2D normals

        # Calculate the edges between points.
        # The call to numpy.roll shifts the entire array by one so that
        # we end up subtracting each next point from the current, wrapping
        # around. This gives us the edges from the next point to the current
        # point.
        normals = numpy.diff(normals, 1, 0)

        # Calculate the length of each edge using standard Pythagoras
        lengths = numpy.sqrt(normals[:, 0] ** 2 + normals[:, 2] ** 2)
        # The normal of a 2D vector is equal to its x and y coordinates swapped
        # and then x inverted. This code does that.
        normals[:, [0, 2]] = normals[:, [2, 0]]
        normals[:, 0] *= -1

        # Normalize the normals.
        normals[:, 0] /= lengths
        normals[:, 2] /= lengths

        return normals

    __color_map = None # type: numpy.ndarray[Any]

    ##  Gets the instance of the VersionUpgradeManager, or creates one.
    @classmethod
    def getColorMap(cls):
        if cls.__color_map is None:
            theme = Application.getInstance().getTheme()
            cls.__color_map = numpy.array([
                theme.getColor("layerview_none").getRgbF(), # NoneType
                theme.getColor("layerview_inset_0").getRgbF(), # Inset0Type
                theme.getColor("layerview_inset_x").getRgbF(), # InsetXType
                theme.getColor("layerview_skin").getRgbF(), # SkinType
                theme.getColor("layerview_support").getRgbF(), # SupportType
                theme.getColor("layerview_skirt").getRgbF(), # SkirtType
                theme.getColor("layerview_infill").getRgbF(), # InfillType
                theme.getColor("layerview_support_infill").getRgbF(), # SupportInfillType
                theme.getColor("layerview_move_combing").getRgbF(), # MoveCombingType
                theme.getColor("layerview_move_retraction").getRgbF(), # MoveRetractionType
                theme.getColor("layerview_support_interface").getRgbF()  # SupportInterfaceType
            ])

        return cls.__color_map
