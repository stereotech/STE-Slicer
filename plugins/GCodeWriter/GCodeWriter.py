import base64

import re  # For escaping characters in the settings.
import json
import copy

from UM.Math.AxisAlignedBox import AxisAlignedBox
from UM.Mesh.MeshWriter import MeshWriter
from UM.Logger import Logger
from UM.Application import Application
from UM.Settings.InstanceContainer import InstanceContainer

from steslicer.Machines.QualityManager import getMachineDefinitionIDForQualitySearch
from steslicer.Utils.Threading import call_on_qt_thread
from steslicer.Snapshot import Snapshot


from PyQt5.QtCore import QBuffer
from UM.i18n import i18nCatalog
catalog = i18nCatalog("steslicer")



##  Writes g-code to a file.
#
#   While this poses as a mesh writer, what this really does is take the g-code
#   in the entire scene and write it to an output device. Since the g-code of a
#   single mesh isn't separable from the rest what with rafts and travel moves
#   and all, it doesn't make sense to write just a single mesh.
#
#   So this plug-in takes the g-code that is stored in the root of the scene
#   node tree, adds a bit of extra information about the profiles and writes
#   that to the output device.
class GCodeWriter(MeshWriter):
    ##  The file format version of the serialised g-code.
    #
    #   It can only read settings with the same version as the version it was
    #   written with. If the file format is changed in a way that breaks reverse
    #   compatibility, increment this version number!
    version = 3

    ##  Dictionary that defines how characters are escaped when embedded in
    #   g-code.
    #
    #   Note that the keys of this dictionary are regex strings. The values are
    #   not.
    escape_characters = {
        re.escape("\\"): "\\\\",  # The escape character.
        re.escape("\n"): "\\n",   # Newlines. They break off the comment.
        re.escape("\r"): "\\r"    # Carriage return. Windows users may need this for visualisation in their editors.
    }

    _setting_keyword = ";SETTING_"

    def __init__(self):
        super().__init__(add_to_recent_files = False)

        self._application = Application.getInstance()

    ##  Writes the g-code for the entire scene to a stream.
    #
    #   Note that even though the function accepts a collection of nodes, the
    #   entire scene is always written to the file since it is not possible to
    #   separate the g-code for just specific nodes.
    #
    #   \param stream The stream to write the g-code to.
    #   \param nodes This is ignored.
    #   \param mode Additional information on how to format the g-code in the
    #   file. This must always be text mode.
    def write(self, stream, nodes, mode = MeshWriter.OutputMode.TextMode):

        if mode != MeshWriter.OutputMode.TextMode:
            Logger.log("e", "GCodeWriter does not support non-text mode.")
            self.setInformation(catalog.i18nc("@error:not supported", "GCodeWriter does not support non-text mode."))
            return False

        active_build_plate = Application.getInstance().getMultiBuildPlateModel().activeBuildPlate
        scene = Application.getInstance().getController().getScene()
        if not hasattr(scene, "gcode_dict"):
            self.setInformation(catalog.i18nc("@warning:status", "Please prepare G-code before exporting."))
            return False
        gcode_dict = getattr(scene, "gcode_dict")
        gcode_list = gcode_dict.get(active_build_plate, None)
        if gcode_list is not None:
            has_settings = False
            preview_image = self._getPreviewImage()
            if preview_image:
                stream.write(preview_image)
            slicer_version = self._getSlicerVersion()
            stream.write(slicer_version)
            printing_mode = self._getPrintingMode()
            stream.write(printing_mode)
            scene_size = self._getSerializedBounding()
            stream.write(scene_size)
            for gcode in gcode_list:
                if gcode[:len(self._setting_keyword)] == self._setting_keyword:
                    has_settings = True
                stream.write(gcode)
            # Serialise the current container stack and put it at the end of the file.
            if not has_settings:
                settings = self._serialiseSettings(Application.getInstance().getGlobalContainerStack())
                stream.write(settings)
            return True

        self.setInformation(catalog.i18nc("@warning:status", "Please prepare G-code before exporting."))

        return False

    ##  Create a new container with container 2 as base and container 1 written over it.
    def _createFlattenedContainerInstance(self, instance_container1, instance_container2):
        flat_container = InstanceContainer(instance_container2.getName())

        # The metadata includes id, name and definition
        flat_container.setMetaData(copy.deepcopy(instance_container2.getMetaData()))

        if instance_container1.getDefinition():
            flat_container.setDefinition(instance_container1.getDefinition().getId())

        for key in instance_container2.getAllKeys():
            flat_container.setProperty(key, "value", instance_container2.getProperty(key, "value"))

        for key in instance_container1.getAllKeys():
            flat_container.setProperty(key, "value", instance_container1.getProperty(key, "value"))

        return flat_container

    ##  Serialises a container stack to prepare it for writing at the end of the
    #   g-code.
    #
    #   The settings are serialised, and special characters (including newline)
    #   are escaped.
    #
    #   \param settings A container stack to serialise.
    #   \return A serialised string of the settings.
    def _serialiseSettings(self, stack):
        container_registry = self._application.getContainerRegistry()
        quality_manager = self._application.getQualityManager()

        prefix = self._setting_keyword + str(GCodeWriter.version) + " "  # The prefix to put before each line.
        prefix_length = len(prefix)

        quality_type = stack.quality.getMetaDataEntry("quality_type")
        container_with_profile = stack.qualityChanges
        if container_with_profile.getId() == "empty_quality_changes":
            # If the global quality changes is empty, create a new one
            quality_name = container_registry.uniqueName(stack.quality.getName())
            container_with_profile = quality_manager._createQualityChanges(quality_type, quality_name, stack, None)

        flat_global_container = self._createFlattenedContainerInstance(stack.userChanges, container_with_profile)
        # If the quality changes is not set, we need to set type manually
        if flat_global_container.getMetaDataEntry("type", None) is None:
            flat_global_container.setMetaDataEntry("type", "quality_changes")

        # Ensure that quality_type is set. (Can happen if we have empty quality changes).
        if flat_global_container.getMetaDataEntry("quality_type", None) is None:
            flat_global_container.setMetaDataEntry("quality_type", stack.quality.getMetaDataEntry("quality_type", "normal"))

        # Get the machine definition ID for quality profiles
        machine_definition_id_for_quality = getMachineDefinitionIDForQualitySearch(stack.definition)
        flat_global_container.setMetaDataEntry("definition", machine_definition_id_for_quality)

        serialized = flat_global_container.serialize()
        data = {"global_quality": serialized}

        all_setting_keys = flat_global_container.getAllKeys()
        for extruder in sorted(stack.extruders.values(), key = lambda k: int(k.getMetaDataEntry("position"))):
            extruder_quality = extruder.qualityChanges
            if extruder_quality.getId() == "empty_quality_changes":
                # Same story, if quality changes is empty, create a new one
                quality_name = container_registry.uniqueName(stack.quality.getName())
                extruder_quality = quality_manager._createQualityChanges(quality_type, quality_name, stack, None)

            flat_extruder_quality = self._createFlattenedContainerInstance(extruder.userChanges, extruder_quality)
            # If the quality changes is not set, we need to set type manually
            if flat_extruder_quality.getMetaDataEntry("type", None) is None:
                flat_extruder_quality.setMetaDataEntry("type", "quality_changes")

            # Ensure that extruder is set. (Can happen if we have empty quality changes).
            if flat_extruder_quality.getMetaDataEntry("position", None) is None:
                flat_extruder_quality.setMetaDataEntry("position", extruder.getMetaDataEntry("position"))

            # Ensure that quality_type is set. (Can happen if we have empty quality changes).
            if flat_extruder_quality.getMetaDataEntry("quality_type", None) is None:
                flat_extruder_quality.setMetaDataEntry("quality_type", extruder.quality.getMetaDataEntry("quality_type", "normal"))

            # Change the default definition
            flat_extruder_quality.setMetaDataEntry("definition", machine_definition_id_for_quality)

            extruder_serialized = flat_extruder_quality.serialize()
            data.setdefault("extruder_quality", []).append(extruder_serialized)

            all_setting_keys.update(flat_extruder_quality.getAllKeys())

        # Check if there is any profiles
        if not all_setting_keys:
            Logger.log("i", "No custom settings found, not writing settings to g-code.")
            return ""

        json_string = json.dumps(data)

        # Escape characters that have a special meaning in g-code comments.
        pattern = re.compile("|".join(GCodeWriter.escape_characters.keys()))

        # Perform the replacement with a regular expression.
        escaped_string = pattern.sub(lambda m: GCodeWriter.escape_characters[re.escape(m.group(0))], json_string)

        # Introduce line breaks so that each comment is no longer than 80 characters. Prepend each line with the prefix.
        result = ""

        # Lines have 80 characters, so the payload of each line is 80 - prefix.
        for pos in range(0, len(escaped_string), 80 - prefix_length):
            result += prefix + escaped_string[pos: pos + 80 - prefix_length] + "\n"
        return result

    def _getSerializedBounding(self):
        aabb = self._application.getSceneBoundingBox() #type: AxisAlignedBox

        return ";MINX:%(MINX).1f\n;MINY:%(MINY).1f\n;MINZ:%(MINZ).1f\n" \
               ";MAXX:%(MAXX).1f\n;MAXY:%(MAXY).1f\n;MAXZ:%(MAXZ).1f\n" % \
               {'MINX': aabb.left.item(),
                'MINY': aabb.back.item(),
                'MINZ': aabb.bottom.item(),
                'MAXX': aabb.right.item(),
                'MAXY': aabb.front.item(),
                'MAXZ': aabb.top.item()}

    def _getSlicerVersion(self):
        version = self._application.getVersion()
        return ";VERSION:%(VERSION)s\n" % \
               {
                'VERSION': version
               }

    def _getPrintingMode(self):
        printing_mode = self._application.getInstance().getGlobalContainerStack().getProperty("printing_mode", "value")
        return ";PRINTING_MODE:[%(MODE)s]\n" % \
               {
                   'MODE': printing_mode
               }
    @call_on_qt_thread  # must be called from the main thread because of OpenGL
    def _createSnapshot(self):
        
        Logger.log("d", "Creating thumbnail image...")
        try:
            snapshot = Snapshot.snapshot(width = 300, height = 300)
        except:
            Logger.logException("w", "Failed to create snapshot image")
            return None

        return snapshot

    def _getPreviewImage(self):
        snapshot = self._createSnapshot()
        if snapshot:
            thumbnail_buffer = QBuffer()
            thumbnail_buffer.open(QBuffer.ReadWrite)
            snapshot.save(thumbnail_buffer, "PNG")
            base64_message = base64.b64encode(thumbnail_buffer.data()).decode('utf-8')
            thumbnail_buffer.close()

            return ";PREVIEW:%(PREVIEW)s\n" % \
                {
                    'PREVIEW': base64_message
                }
        else:
            return None
