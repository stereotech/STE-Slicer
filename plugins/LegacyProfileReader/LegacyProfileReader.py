# Copyright (c) 2017 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import configparser  # For reading the legacy profile INI files.
import io
import json  # For reading the Dictionary of Doom.
import math  # For mathematical operations included in the Dictionary of Doom.
import os.path  # For concatenating the path to the plugin and the relative path to the Dictionary of Doom.

from UM.Application import Application  # To get the machine manager to create the new profile in.
from UM.Logger import Logger  # Logging errors.
from UM.PluginRegistry import PluginRegistry  # For getting the path to this plugin's directory.
from UM.Settings.ContainerRegistry import ContainerRegistry #To create unique profile IDs.
from UM.Settings.InstanceContainer import InstanceContainer  # The new profile to make.
from cura.ReaderWriters.ProfileReader import ProfileReader  # The plug-in type to implement.


##  A plugin that reads profile data from legacy Cura versions.
#
#   It reads a profile from an .ini file, and performs some translations on it.
#   Not all translations are correct, mind you, but it is a best effort.
class LegacyProfileReader(ProfileReader):
    ##  Initialises the legacy profile reader.
    #
    #   This does nothing since the only other function is basically stateless.
    def __init__(self):
        super().__init__()

    ##  Prepares the default values of all legacy settings.
    #
    #   These are loaded from the Dictionary of Doom.
    #
    #   \param json The JSON file to load the default setting values from. This
    #   should not be a URL but a pre-loaded JSON handle.
    #   \return A dictionary of the default values of the legacy Cura version.
    def prepareDefaults(self, json):
        defaults = {}
        for key in json["defaults"]:  # We have to copy over all defaults from the JSON handle to a normal dict.
            defaults[key] = json["defaults"][key]
        return defaults

    ##  Prepares the local variables that can be used in evaluation of computing
    #   new setting values from the old ones.
    #
    #   This fills a dictionary with all settings from the legacy Cura version
    #   and their values, so that they can be used in evaluating the new setting
    #   values as Python code.
    #
    #   \param config_parser The ConfigParser that finds the settings in the
    #   legacy profile.
    #   \param config_section The section in the profile where the settings
    #   should be found.
    #   \param defaults The default values for all settings in the legacy Cura.
    #   \return A set of local variables, one for each setting in the legacy
    #   profile.
    def prepareLocals(self, config_parser, config_section, defaults):
        copied_locals = defaults.copy()  # Don't edit the original!
        for option in config_parser.options(config_section):
            copied_locals[option] = config_parser.get(config_section, option)
        return copied_locals

    ##  Reads a legacy Cura profile from a file and returns it.
    #
    #   \param file_name The file to read the legacy Cura profile from.
    #   \return The legacy Cura profile that was in the file, if any. If the
    #   file could not be read or didn't contain a valid profile, \code None
    #   \endcode is returned.
    def read(self, file_name):
        if file_name.split(".")[-1] != "ini":
            return None
        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if not global_container_stack:
            return None

        multi_extrusion = global_container_stack.getProperty("machine_extruder_count", "value") > 1
        if multi_extrusion:
            Logger.log("e", "Unable to import legacy profile %s. Multi extrusion is not supported", file_name)
            raise Exception("Unable to import legacy profile. Multi extrusion is not supported")

        Logger.log("i", "Importing legacy profile from file " + file_name + ".")
        container_registry = ContainerRegistry.getInstance()
        profile_id = container_registry.uniqueName("Imported Legacy Profile")
        profile = InstanceContainer(profile_id)  # Create an empty profile.

        parser = configparser.ConfigParser(interpolation = None)
        try:
            parser.read([file_name])  # Parse the INI file.
        except Exception as e:
            Logger.log("e", "Unable to open legacy profile %s: %s", file_name, str(e))
            return None

        # Legacy Cura saved the profile under the section "profile_N" where N is the ID of a machine, except when you export in which case it saves it in the section "profile".
        # Since importing multiple machine profiles is out of scope, just import the first section we find.
        section = ""
        for found_section in parser.sections():
            if found_section.startswith("profile"):
                section = found_section
                break
        if not section:  # No section starting with "profile" was found. Probably not a proper INI file.
            return None

        try:
            with open(os.path.join(PluginRegistry.getInstance().getPluginPath("LegacyProfileReader"), "DictionaryOfDoom.json"), "r", encoding = "utf-8") as f:
                dict_of_doom = json.load(f)  # Parse the Dictionary of Doom.
        except IOError as e:
            Logger.log("e", "Could not open DictionaryOfDoom.json for reading: %s", str(e))
            return None
        except Exception as e:
            Logger.log("e", "Could not parse DictionaryOfDoom.json: %s", str(e))
            return None

        defaults = self.prepareDefaults(dict_of_doom)
        legacy_settings = self.prepareLocals(parser, section, defaults) #Gets the settings from the legacy profile.

        #Check the target version in the Dictionary of Doom with this application version.
        if "target_version" not in dict_of_doom:
            Logger.log("e", "Dictionary of Doom has no target version. Is it the correct JSON file?")
            return None
        if InstanceContainer.Version != dict_of_doom["target_version"]:
            Logger.log("e", "Dictionary of Doom of legacy profile reader (version %s) is not in sync with the current instance container version (version %s)!", dict_of_doom["target_version"], str(InstanceContainer.Version))
            return None

        if "translation" not in dict_of_doom:
            Logger.log("e", "Dictionary of Doom has no translation. Is it the correct JSON file?")
            return None
        current_printer_definition = global_container_stack.definition
        quality_definition = current_printer_definition.getMetaDataEntry("quality_definition")
        if not quality_definition:
            quality_definition = current_printer_definition.getId()
        profile.setDefinition(quality_definition)
        for new_setting in dict_of_doom["translation"]:  # Evaluate all new settings that would get a value from the translations.
            old_setting_expression = dict_of_doom["translation"][new_setting]
            compiled = compile(old_setting_expression, new_setting, "eval")
            try:
                new_value = eval(compiled, {"math": math}, legacy_settings)  # Pass the legacy settings as local variables to allow access to in the evaluation.
                value_using_defaults = eval(compiled, {"math": math}, defaults)  #Evaluate again using only the default values to try to see if they are default.
            except Exception:  # Probably some setting name that was missing or something else that went wrong in the ini file.
                Logger.log("w", "Setting " + new_setting + " could not be set because the evaluation failed. Something is probably missing from the imported legacy profile.")
                continue
            definitions = current_printer_definition.findDefinitions(key = new_setting)
            if definitions:
                if new_value != value_using_defaults and definitions[0].default_value != new_value:  # Not equal to the default in the new Cura OR the default in the legacy Cura.
                    profile.setProperty(new_setting, "value", new_value)  # Store the setting in the profile!

        if len(profile.getAllKeys()) == 0:
            Logger.log("i", "A legacy profile was imported but everything evaluates to the defaults, creating an empty profile.")

        profile.setMetaDataEntry("type", "profile")
        # don't know what quality_type it is based on, so use "normal" by default
        profile.setMetaDataEntry("quality_type", "normal")
        profile.setName(profile_id)
        profile.setDirty(True)

        #Serialise and deserialise in order to perform the version upgrade.
        parser = configparser.ConfigParser(interpolation = None)
        data = profile.serialize()
        parser.read_string(data)
        parser["general"]["version"] = "1"
        if parser.has_section("values"):
            parser["settings"] = parser["values"]
            del parser["values"]
        stream = io.StringIO()
        parser.write(stream)
        data = stream.getvalue()
        profile.deserialize(data)

        # The definition can get reset to fdmprinter during the deserialization's upgrade. Here we set the definition
        # again.
        profile.setDefinition(quality_definition)

        #We need to return one extruder stack and one global stack.
        global_container_id = container_registry.uniqueName("Global Imported Legacy Profile")
        global_profile = profile.duplicate(new_id = global_container_id, new_name = profile_id) #Needs to have the same name as the extruder profile.
        global_profile.setDirty(True)

        profile_definition = "fdmprinter"
        from UM.Util import parseBool
        if parseBool(global_container_stack.getMetaDataEntry("has_machine_quality", "False")):
            profile_definition = global_container_stack.getMetaDataEntry("quality_definition")
            if not profile_definition:
                profile_definition = global_container_stack.definition.getId()
        global_profile.setDefinition(profile_definition)

        return [global_profile]
