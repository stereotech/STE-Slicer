

import QtQuick 2.1
import QtQuick.Controls 1.1
import QtQuick.Layouts 1.1
import QtQuick.Controls.Styles 1.1

import UM 1.1 as UM
import SteSlicer 1.0 as SteSlicer

UM.PreferencesPage
{
    //: General configuration page title
    title: catalog.i18nc("@title:tab","General")
    id: generalPreferencesPage

    function setDefaultLanguage(languageCode)
    {
        //loops trough the languageList and sets the language using the languageCode
        for(var i = 0; i < languageList.count; i++)
        {
            if (languageComboBox.model.get(i).code == languageCode)
            {
                languageComboBox.currentIndex = i
            }
        }
    }

    function setDefaultTheme(defaultThemeCode)
    {
        for(var i = 0; i < themeList.count; i++)
        {
            if (themeComboBox.model.get(i).code == defaultThemeCode)
            {
                themeComboBox.currentIndex = i
            }
        }
    }

    function setDefaultDiscardOrKeepProfile(code)
    {
        for (var i = 0; i < choiceOnProfileOverrideDropDownButton.model.count; i++)
        {
            if (choiceOnProfileOverrideDropDownButton.model.get(i).code == code)
            {
                choiceOnProfileOverrideDropDownButton.currentIndex = i;
                break;
            }
        }
    }

    function setDefaultOpenProjectOption(code)
    {
        for (var i = 0; i < choiceOnOpenProjectDropDownButton.model.count; ++i)
        {
            if (choiceOnOpenProjectDropDownButton.model.get(i).code == code)
            {
                choiceOnOpenProjectDropDownButton.currentIndex = i
                break;
            }
        }
    }

    function reset()
    {
        UM.Preferences.resetPreference("general/language")
        var defaultLanguage = UM.Preferences.getValue("general/language")
        setDefaultLanguage(defaultLanguage)

        UM.Preferences.resetPreference("general/theme")
        var defaultTheme = UM.Preferences.getValue("general/theme")
        setDefaultTheme(defaultTheme)

        UM.Preferences.resetPreference("physics/automatic_push_free")
        pushFreeCheckbox.checked = boolCheck(UM.Preferences.getValue("physics/automatic_push_free"))
        UM.Preferences.resetPreference("physics/automatic_drop_down")
        dropDownCheckbox.checked = boolCheck(UM.Preferences.getValue("physics/automatic_drop_down"))
        UM.Preferences.resetPreference("mesh/scale_to_fit")
        scaleToFitCheckbox.checked = boolCheck(UM.Preferences.getValue("mesh/scale_to_fit"))
        UM.Preferences.resetPreference("mesh/scale_tiny_meshes")
        scaleTinyCheckbox.checked = boolCheck(UM.Preferences.getValue("mesh/scale_tiny_meshes"))
        UM.Preferences.resetPreference("steslicer/select_models_on_load")
        selectModelsOnLoadCheckbox.checked = boolCheck(UM.Preferences.getValue("steslicer/select_models_on_load"))
        UM.Preferences.resetPreference("steslicer/jobname_prefix")
        prefixJobNameCheckbox.checked = boolCheck(UM.Preferences.getValue("steslicer/jobname_prefix"))
        UM.Preferences.resetPreference("view/show_overhang");
        showOverhangCheckbox.checked = boolCheck(UM.Preferences.getValue("view/show_overhang"))
        UM.Preferences.resetPreference("view/center_on_select");
        centerOnSelectCheckbox.checked = boolCheck(UM.Preferences.getValue("view/center_on_select"))
        UM.Preferences.resetPreference("view/invert_zoom");
        invertZoomCheckbox.checked = boolCheck(UM.Preferences.getValue("view/invert_zoom"))
        UM.Preferences.resetPreference("view/zoom_to_mouse");
        zoomToMouseCheckbox.checked = boolCheck(UM.Preferences.getValue("view/zoom_to_mouse"))
        UM.Preferences.resetPreference("view/top_layer_count");
        topLayerCountCheckbox.checked = boolCheck(UM.Preferences.getValue("view/top_layer_count"))

        UM.Preferences.resetPreference("steslicer/choice_on_profile_override")
        setDefaultDiscardOrKeepProfile(UM.Preferences.getValue("steslicer/choice_on_profile_override"))

        UM.Preferences.resetPreference("steslicer/choice_on_open_project")
        setDefaultOpenProjectOption(UM.Preferences.getValue("steslicer/choice_on_open_project"))

        if (pluginExistsAndEnabled("SliceInfoPlugin")) {
            UM.Preferences.resetPreference("info/send_slice_info")
            sendDataCheckbox.checked = boolCheck(UM.Preferences.getValue("info/send_slice_info"))
        }
        if (pluginExistsAndEnabled("UpdateChecker")) {
            UM.Preferences.resetPreference("info/automatic_update_check")
            checkUpdatesCheckbox.checked = boolCheck(UM.Preferences.getValue("info/automatic_update_check"))
        }
    }

    function pluginExistsAndEnabled(pluginName)
    {
        var pluginItem = plugins.find("id", pluginName)
        if (pluginItem > -1)
        {
            return plugins.getItem(pluginItem).enabled
        }
        return false
    }

    ScrollView
    {
        width: parent.width
        height: parent.height

        flickableItem.flickableDirection: Flickable.VerticalFlick;

        Column
        {
            //: Model used to check if a plugin exists
            UM.PluginsModel { id: plugins }

            //: Language selection label
            UM.I18nCatalog{id: catalog; name:"steslicer"}

            Label
            {
                font.bold: true
                text: catalog.i18nc("@label","Interface")
            }

            GridLayout
            {
                id: interfaceGrid
                columns: 4

                Label
                {
                    id: languageLabel
                    text: catalog.i18nc("@label","Language:")
                    anchors.verticalCenter: languageComboBox.verticalCenter
                }

                ComboBox
                {
                    id: languageComboBox
                    model: ListModel
                    {
                        id: languageList

                        Component.onCompleted: {
                            append({ text: "English", code: "en_US" })                            
                            append({ text: "Русский", code: "ru_RU" })

                            var date_object = new Date();
                            if (date_object.getUTCMonth() == 8 && date_object.getUTCDate() == 19) //Only add Pirate on the 19th of September.
                            {
                                append({ text: "Pirate", code: "en_7S" })
                            }
                        }
                    }

                    currentIndex:
                    {
                        var code = UM.Preferences.getValue("general/language");
                        for(var i = 0; i < languageList.count; ++i)
                        {
                            if(model.get(i).code == code)
                            {
                                return i
                            }
                        }
                    }
                    onActivated: UM.Preferences.setValue("general/language", model.get(index).code)

                    Component.onCompleted:
                    {
                        // Because ListModel is stupid and does not allow using qsTr() for values.
                        for(var i = 0; i < languageList.count; ++i)
                        {
                            languageList.setProperty(i, "text", catalog.i18n(languageList.get(i).text));
                        }

                        // Glorious hack time. ComboBox does not update the text properly after changing the
                        // model. So change the indices around to force it to update.
                        currentIndex += 1;
                        currentIndex -= 1;
                    }
                }

                Label
                {
                    id: currencyLabel
                    text: catalog.i18nc("@label","Currency:")
                    anchors.verticalCenter: currencyField.verticalCenter
                }

                TextField
                {
                    id: currencyField
                    text: UM.Preferences.getValue("steslicer/currency")
                    onTextChanged: UM.Preferences.setValue("steslicer/currency", text)
                }

                Label
                {
                    id: themeLabel
                    text: catalog.i18nc("@label","Theme:")
                    anchors.verticalCenter: themeComboBox.verticalCenter
                }

                ComboBox
                {
                    id: themeComboBox

                    model: ListModel
                    {
                        id: themeList

                        Component.onCompleted: {
                            var themes = UM.Theme.getThemes()
                            for (var i = 0; i < themes.length; i++)
                            {
                                append({ text: themes[i].name.toString(), code: themes[i].id.toString() });
                            }
                        }
                    }

                    currentIndex:
                    {
                        var code = UM.Preferences.getValue("general/theme");
                        for(var i = 0; i < themeList.count; ++i)
                        {
                            if(model.get(i).code == code)
                            {
                                return i
                            }
                        }
                        return 0;
                    }
                    onActivated: UM.Preferences.setValue("general/theme", model.get(index).code)

                    Component.onCompleted:
                    {
                        // Because ListModel is stupid and does not allow using qsTr() for values.
                        for(var i = 0; i < themeList.count; ++i)
                        {
                            themeList.setProperty(i, "text", catalog.i18n(themeList.get(i).text));
                        }

                        // Glorious hack time. ComboBox does not update the text properly after changing the
                        // model. So change the indices around to force it to update.
                        currentIndex += 1;
                        currentIndex -= 1;
                    }

                }
            }

            Label
            {
                id: languageCaption

                //: Language change warning
                text: catalog.i18nc("@label", "You will need to restart the application for these changes to have effect.")
                wrapMode: Text.WordWrap
                font.italic: true
            }

            Item
            {
                //: Spacer
                height: UM.Theme.getSize("default_margin").height
                width: UM.Theme.getSize("default_margin").width
            }

            UM.TooltipArea
            {
                width: childrenRect.width;
                height: childrenRect.height;

                text: catalog.i18nc("@info:tooltip", "Slice automatically when changing settings.")

                CheckBox
                {
                    id: autoSliceCheckbox
                    checked: boolCheck(UM.Preferences.getValue("general/auto_slice"))
                    onClicked: UM.Preferences.setValue("general/auto_slice", checked)

                    text: catalog.i18nc("@option:check", "Slice automatically");
                }
            }

            Item
            {
                //: Spacer
                height: UM.Theme.getSize("default_margin").height
                width: UM.Theme.getSize("default_margin").width
            }

            Label
            {
                font.bold: true
                text: catalog.i18nc("@label", "Viewport behavior")
            }

            UM.TooltipArea
            {
                width: childrenRect.width;
                height: childrenRect.height;

                text: catalog.i18nc("@info:tooltip", "Highlight unsupported areas of the model in red. Without support these areas will not print properly.")

                CheckBox
                {
                    id: showOverhangCheckbox

                    checked: boolCheck(UM.Preferences.getValue("view/show_overhang"))
                    onClicked: UM.Preferences.setValue("view/show_overhang",  checked)

                    text: catalog.i18nc("@option:check", "Display overhang");
                }
            }

            UM.TooltipArea {
                width: childrenRect.width;
                height: childrenRect.height;
                text: catalog.i18nc("@info:tooltip", "Moves the camera so the model is in the center of the view when a model is selected")

                CheckBox
                {
                    id: centerOnSelectCheckbox
                    text: catalog.i18nc("@action:button","Center camera when item is selected");
                    checked: boolCheck(UM.Preferences.getValue("view/center_on_select"))
                    onClicked: UM.Preferences.setValue("view/center_on_select",  checked)
                }
            }

            UM.TooltipArea {
                width: childrenRect.width;
                height: childrenRect.height;
                text: catalog.i18nc("@info:tooltip", "Should the default zoom behavior of STE Slicer be inverted?")

                CheckBox
                {
                    id: invertZoomCheckbox
                    text: catalog.i18nc("@action:button", "Invert the direction of camera zoom.");
                    checked: boolCheck(UM.Preferences.getValue("view/invert_zoom"))
                    onClicked: UM.Preferences.setValue("view/invert_zoom",  checked)
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width;
                height: childrenRect.height;
                text: catalog.i18nc("@info:tooltip", "Should zooming move in the direction of the mouse?")

                CheckBox
                {
                    id: zoomToMouseCheckbox
                    text: catalog.i18nc("@action:button", "Zoom toward mouse direction");
                    checked: boolCheck(UM.Preferences.getValue("view/zoom_to_mouse"))
                    onClicked: UM.Preferences.setValue("view/zoom_to_mouse", checked)
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip", "Should models on the platform be moved so that they no longer intersect?")

                CheckBox
                {
                    id: pushFreeCheckbox
                    text: catalog.i18nc("@option:check", "Ensure models are kept apart")
                    checked: boolCheck(UM.Preferences.getValue("physics/automatic_push_free"))
                    onCheckedChanged: UM.Preferences.setValue("physics/automatic_push_free", checked)
                }
            }
            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip", "Should models on the platform be moved down to touch the build plate?")

                CheckBox
                {
                    id: dropDownCheckbox
                    text: catalog.i18nc("@option:check", "Automatically drop models to the build plate")
                    checked: boolCheck(UM.Preferences.getValue("physics/automatic_drop_down"))
                    onCheckedChanged: UM.Preferences.setValue("physics/automatic_drop_down", checked)
                }
            }


            UM.TooltipArea
            {
                width: childrenRect.width;
                height: childrenRect.height;

                text: catalog.i18nc("@info:tooltip","Show caution message in g-code reader.")

                CheckBox
                {
                    id: gcodeShowCautionCheckbox

                    checked: boolCheck(UM.Preferences.getValue("gcodereader/show_caution"))
                    onClicked: UM.Preferences.setValue("gcodereader/show_caution", checked)

                    text: catalog.i18nc("@option:check","Caution message in g-code reader");
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip", "Should layer be forced into compatibility mode?")

                CheckBox
                {
                    id: forceLayerViewCompatibilityModeCheckbox
                    text: catalog.i18nc("@option:check", "Force layer view compatibility mode (restart required)")
                    checked: boolCheck(UM.Preferences.getValue("view/force_layer_view_compatibility_mode"))
                    onCheckedChanged: UM.Preferences.setValue("view/force_layer_view_compatibility_mode", checked)
                }
            }

            Item
            {
                //: Spacer
                height: UM.Theme.getSize("default_margin").height
                width: UM.Theme.getSize("default_margin").height
            }

            Label
            {
                font.bold: true
                text: catalog.i18nc("@label","Opening and saving files")
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip","Should models be scaled to the build volume if they are too large?")

                CheckBox
                {
                    id: scaleToFitCheckbox
                    text: catalog.i18nc("@option:check","Scale large models")
                    checked: boolCheck(UM.Preferences.getValue("mesh/scale_to_fit"))
                    onCheckedChanged: UM.Preferences.setValue("mesh/scale_to_fit", checked)
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip","An model may appear extremely small if its unit is for example in meters rather than millimeters. Should these models be scaled up?")

                CheckBox
                {
                    id: scaleTinyCheckbox
                    text: catalog.i18nc("@option:check","Scale extremely small models")
                    checked: boolCheck(UM.Preferences.getValue("mesh/scale_tiny_meshes"))
                    onCheckedChanged: UM.Preferences.setValue("mesh/scale_tiny_meshes", checked)
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip","Should models be selected after they are loaded?")

                CheckBox
                {
                    id: selectModelsOnLoadCheckbox
                    text: catalog.i18nc("@option:check","Select models when loaded")
                    checked: boolCheck(UM.Preferences.getValue("steslicer/select_models_on_load"))
                    onCheckedChanged: UM.Preferences.setValue("steslicer/select_models_on_load", checked)
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip", "Should a prefix based on the printer name be added to the print job name automatically?")

                CheckBox
                {
                    id: prefixJobNameCheckbox
                    text: catalog.i18nc("@option:check", "Add machine prefix to job name")
                    checked: boolCheck(UM.Preferences.getValue("steslicer/jobname_prefix"))
                    onCheckedChanged: UM.Preferences.setValue("steslicer/jobname_prefix", checked)
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip", "Should a summary be shown when saving a project file?")

                CheckBox
                {
                    text: catalog.i18nc("@option:check", "Show summary dialog when saving project")
                    checked: boolCheck(UM.Preferences.getValue("steslicer/dialog_on_project_save"))
                    onCheckedChanged: UM.Preferences.setValue("steslicer/dialog_on_project_save", checked)
                }
            }

            UM.TooltipArea
            {
                width: childrenRect.width
                height: childrenRect.height
                text: catalog.i18nc("@info:tooltip", "Default behavior when opening a project file")

                Column
                {
                    spacing: 4 * screenScaleFactor

                    Label
                    {
                        text: catalog.i18nc("@window:text", "Default behavior when opening a project file: ")
                    }

                    ComboBox
                    {
                        id: choiceOnOpenProjectDropDownButton
                        width: 200 * screenScaleFactor

                        model: ListModel
                        {
                            id: openProjectOptionModel

                            Component.onCompleted:
                            {
                                append({ text: catalog.i18nc("@option:openProject", "Always ask me this"), code: "always_ask" })
                                append({ text: catalog.i18nc("@option:openProject", "Always open as a project"), code: "open_as_project" })
                                append({ text: catalog.i18nc("@option:openProject", "Always import models"), code: "open_as_model" })
                            }
                        }

                        currentIndex:
                        {
                            var index = 0;
                            var currentChoice = UM.Preferences.getValue("steslicer/choice_on_open_project");
                            for (var i = 0; i < model.count; ++i)
                            {
                                if (model.get(i).code == currentChoice)
                                {
                                    index = i;
                                    break;
                                }
                            }
                            return index;
                        }

                        onActivated: UM.Preferences.setValue("steslicer/choice_on_open_project", model.get(index).code)
                    }
                }
            }

            Item
            {
                //: Spacer
                height: UM.Theme.getSize("default_margin").height
                width: UM.Theme.getSize("default_margin").width
            }

            UM.TooltipArea
            {
                width: childrenRect.width;
                height: childrenRect.height;

                text: catalog.i18nc("@info:tooltip", "When you have made changes to a profile and switched to a different one, a dialog will be shown asking whether you want to keep your modifications or not, or you can choose a default behaviour and never show that dialog again.")

                Column
                {
                    spacing: 4 * screenScaleFactor

                    Label
                    {
                        font.bold: true
                        text: catalog.i18nc("@label", "Profiles")
                    }

                    Label
                    {
                        text: catalog.i18nc("@window:text", "Default behavior for changed setting values when switching to a different profile: ")
                    }

                    ComboBox
                    {
                        id: choiceOnProfileOverrideDropDownButton
                        width: 200 * screenScaleFactor

                        model: ListModel
                        {
                            id: discardOrKeepProfileListModel

                            Component.onCompleted:
                            {
                                append({ text: catalog.i18nc("@option:discardOrKeep", "Always ask me this"), code: "always_ask" })
                                append({ text: catalog.i18nc("@option:discardOrKeep", "Always discard changed settings"), code: "always_discard" })
                                append({ text: catalog.i18nc("@option:discardOrKeep", "Always transfer changed settings to new profile"), code: "always_keep" })
                            }
                        }

                        currentIndex:
                        {
                            var index = 0;
                            var code = UM.Preferences.getValue("steslicer/choice_on_profile_override");
                            for (var i = 0; i < model.count; ++i)
                            {
                                if (model.get(i).code == code)
                                {
                                    index = i;
                                    break;
                                }
                            }
                            return index;
                        }
                        onActivated: UM.Preferences.setValue("steslicer/choice_on_profile_override", model.get(index).code)
                    }
                }
            }

            Item
            {
                //: Spacer
                height: UM.Theme.getSize("default_margin").height
                width: UM.Theme.getSize("default_margin").height
            }

            Label
            {
                font.bold: true
                visible: checkUpdatesCheckbox.visible || sendDataCheckbox.visible
                text: catalog.i18nc("@label","Privacy")
            }

            UM.TooltipArea
            {
                visible: pluginExistsAndEnabled("UpdateChecker")
                width: childrenRect.width
                height: visible ? childrenRect.height : 0
                text: catalog.i18nc("@info:tooltip","Should STE Slicer check for updates when the program is started?")

                CheckBox
                {
                    id: checkUpdatesCheckbox
                    text: catalog.i18nc("@option:check","Check for updates on start")
                    checked: boolCheck(UM.Preferences.getValue("info/automatic_update_check"))
                    onCheckedChanged: UM.Preferences.setValue("info/automatic_update_check", checked)
                }
            }

            UM.TooltipArea
            {
                visible: pluginExistsAndEnabled("SliceInfoPlugin")
                width: childrenRect.width
                height: visible ? childrenRect.height : 0
                text: catalog.i18nc("@info:tooltip","Should anonymous data about your print be sent to Stereotech? Note, no models, IP addresses or other personally identifiable information is sent or stored.")

                CheckBox
                {
                    id: sendDataCheckbox
                    text: catalog.i18nc("@option:check","Send (anonymous) print information")
                    checked: boolCheck(UM.Preferences.getValue("info/send_slice_info"))
                    onCheckedChanged: UM.Preferences.setValue("info/send_slice_info", checked)
                }

                Button
                {
                    id: showMoreInfo
                    anchors.top: sendDataCheckbox.bottom
                    text: catalog.i18nc("@action:button", "More information")
                    onClicked:
                    {
                        SteSlicerApplication.showMoreInformationDialogForAnonymousDataCollection();
                    }
                }
            }

            Item
            {
                //: Spacer
                height: UM.Theme.getSize("default_margin").height
                width: UM.Theme.getSize("default_margin").height
            }

            Connections
            {
                target: UM.Preferences
                onPreferenceChanged:
                {
                    sendDataCheckbox.checked = boolCheck(UM.Preferences.getValue("info/send_slice_info"))
                }
            }
        }
    }
}
