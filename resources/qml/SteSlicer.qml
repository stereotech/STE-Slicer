

import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Controls.Styles 1.4
import QtQuick.Layouts 1.1
import QtQuick.Dialogs 1.2
import QtGraphicalEffects 1.0

import UM 1.3 as UM
import SteSlicer 1.0 as SteSlicer

import "Menus"

UM.MainWindow
{
    id: base
    //: STE Slicer application window title
    title: catalog.i18nc("@title:window","Stereotech STE Slicer");
    viewportRect: Qt.rect(0, 0, 1.0, 1.0)
    property bool showPrintMonitor: false

    backgroundColor: UM.Theme.getColor("viewport_background")
    // This connection is here to support legacy printer output devices that use the showPrintMonitor signal on Application to switch to the monitor stage
    // It should be phased out in newer plugin versions.
    Connections
    {
        target: SteSlicerApplication
        onShowPrintMonitor: {
            if (show) {
                UM.Controller.setActiveStage("MonitorStage")
            } else {
                UM.Controller.setActiveStage("PrepareStage")
            }
        }
    }

    onWidthChanged:
    {
        // If slidebar is collapsed then it should be invisible
        // otherwise after the main_window resize the sidebar will be fully re-drawn
        if (sidebar.collapsed){
            if (sidebar.visible == true){
                sidebar.visible = false
                sidebar.initialWidth = 0
            }
        }
        else{
            if (sidebar.visible == false){
                sidebar.visible = true
                sidebar.initialWidth = UM.Theme.getSize("sidebar").width
            }
        }
    }

    Component.onCompleted:
    {
        SteSlicerApplication.setMinimumWindowSize(UM.Theme.getSize("window_minimum_size"))
        // Workaround silly issues with QML Action's shortcut property.
        //
        // Currently, there is no way to define shortcuts as "Application Shortcut".
        // This means that all Actions are "Window Shortcuts". The code for this
        // implements a rather naive check that just checks if any of the action's parents
        // are a window. Since the "Actions" object is a singleton it has no parent by
        // default. If we set its parent to something contained in this window, the
        // shortcut will activate properly because one of its parents is a window.
        //
        // This has been fixed for QtQuick Controls 2 since the Shortcut item has a context property.
        SteSlicer.Actions.parent = backgroundItem
        SteSlicerApplication.purgeWindows()
    }

    Item
    {
        id: backgroundItem;
        anchors.fill: parent;
        UM.I18nCatalog{id: catalog; name:"steslicer"}

        signal hasMesh(string name) //this signal sends the filebase name so it can be used for the JobSpecs.qml
        function getMeshName(path){
            //takes the path the complete path of the meshname and returns only the filebase
            var fileName = path.slice(path.lastIndexOf("/") + 1)
            var fileBase = fileName.slice(0, fileName.indexOf("."))
            return fileBase
        }

        //DeleteSelection on the keypress backspace event
        Keys.onPressed: {
            if (event.key == Qt.Key_Backspace)
            {
                SteSlicer.Actions.deleteSelection.trigger()
            }
        }

        UM.ApplicationMenu
        {
            id: menu
            window: base

            Menu
            {
                id: fileMenu
                title: catalog.i18nc("@title:menu menubar:toplevel","&File");
                MenuItem
                {
                    id: newProjectMenu
                    action: SteSlicer.Actions.newProject;
                }

                MenuItem
                {
                    id: openMenu
                    action: SteSlicer.Actions.open;
                }

                RecentFilesMenu { }

                MenuItem
                {
                    id: saveWorkspaceMenu
                    text: catalog.i18nc("@title:menu menubar:file","&Save...")
                    onTriggered:
                    {
                        var args = { "filter_by_machine": false, "file_type": "workspace", "preferred_mimetypes": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml" };
                        if(UM.Preferences.getValue("steslicer/dialog_on_project_save"))
                        {
                            saveWorkspaceDialog.args = args;
                            saveWorkspaceDialog.open()
                        }
                        else
                        {
                            UM.OutputDeviceManager.requestWriteToDevice("local_file", PrintInformation.jobName, args)
                        }
                    }
                }

                MenuSeparator { }

                MenuItem
                {
                    id: saveAsMenu
                    text: catalog.i18nc("@title:menu menubar:file", "&Export...")
                    onTriggered:
                    {
                        var localDeviceId = "local_file";
                        UM.OutputDeviceManager.requestWriteToDevice(localDeviceId, PrintInformation.jobName, { "filter_by_machine": false, "preferred_mimetypes": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"});
                    }
                }

                MenuItem
                {
                    id: exportSelectionMenu
                    text: catalog.i18nc("@action:inmenu menubar:file", "Export Selection...");
                    enabled: UM.Selection.hasSelection;
                    iconName: "document-save-as";
                    onTriggered: UM.OutputDeviceManager.requestWriteSelectionToDevice("local_file", PrintInformation.jobName, { "filter_by_machine": false, "preferred_mimetypes": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"});
                }

                MenuSeparator { }

                MenuItem
                {
                    id: reloadAllMenu
                    action: SteSlicer.Actions.reloadAll;
                }

                MenuSeparator { }

                MenuItem { action: SteSlicer.Actions.quit; }
            }

            Menu
            {
                title: catalog.i18nc("@title:menu menubar:toplevel","&Edit");

                MenuItem { action: SteSlicer.Actions.undo; }
                MenuItem { action: SteSlicer.Actions.redo; }
                MenuSeparator { }
                MenuItem { action: SteSlicer.Actions.selectAll; }
                MenuItem { action: SteSlicer.Actions.arrangeAll; }
                MenuItem { action: SteSlicer.Actions.deleteSelection; }
                MenuItem { action: SteSlicer.Actions.deleteAll; }
                MenuItem { action: SteSlicer.Actions.resetAllTranslation; }
                MenuItem { action: SteSlicer.Actions.resetAll; }
                MenuSeparator { }
                MenuItem { action: SteSlicer.Actions.groupObjects;}
                MenuItem { action: SteSlicer.Actions.mergeObjects;}
                MenuItem { action: SteSlicer.Actions.unGroupObjects;}
            }

            ViewMenu { title: catalog.i18nc("@title:menu", "&View") }

            Menu
            {
                id: settingsMenu
                title: catalog.i18nc("@title:menu", "&Settings")

                PrinterMenu { title: catalog.i18nc("@title:menu menubar:settings", "&Printer") }

                Instantiator
                {
                    model: SteSlicer.ExtrudersModel { simpleNames: true }
                    Menu {
                        title: model.name

                        NozzleMenu { title: SteSlicer.MachineManager.activeDefinitionVariantsName; visible: SteSlicer.MachineManager.hasVariants; extruderIndex: index }
                        MaterialMenu { title: catalog.i18nc("@title:menu", "&Material"); visible: SteSlicer.MachineManager.hasMaterials; extruderIndex: index }

                        MenuSeparator
                        {
                            visible: SteSlicer.MachineManager.hasVariants || SteSlicer.MachineManager.hasMaterials
                        }

                        MenuItem
                        {
                            text: catalog.i18nc("@action:inmenu", "Set as Active Extruder")
                            onTriggered: SteSlicer.MachineManager.setExtruderIndex(model.index)
                        }

                        MenuItem
                        {
                            text: catalog.i18nc("@action:inmenu", "Enable Extruder")
                            onTriggered: SteSlicer.MachineManager.setExtruderEnabled(model.index, true)
                            visible: !SteSlicer.MachineManager.getExtruder(model.index).isEnabled
                        }

                        MenuItem
                        {
                            text: catalog.i18nc("@action:inmenu", "Disable Extruder")
                            onTriggered: SteSlicer.MachineManager.setExtruderEnabled(model.index, false)
                            visible: SteSlicer.MachineManager.getExtruder(model.index).isEnabled
                            enabled: SteSlicer.MachineManager.numberExtrudersEnabled > 1
                        }

                    }
                    onObjectAdded: settingsMenu.insertItem(index, object)
                    onObjectRemoved: settingsMenu.removeItem(object)
                }

                // TODO Only show in dev mode. Remove check when feature ready
                BuildplateMenu { title: catalog.i18nc("@title:menu", "&Build plate"); visible: SteSlicerSDKVersion == "dev" ? SteSlicer.MachineManager.hasVariantBuildplates : false }
                ProfileMenu { title: catalog.i18nc("@title:settings", "&Profile"); }

                MenuSeparator { }

                MenuItem { action: SteSlicer.Actions.configureSettingVisibility }
            }

            Menu
            {
                id: extension_menu
                title: catalog.i18nc("@title:menu menubar:toplevel","E&xtensions");

                Instantiator
                {
                    id: extensions
                    model: UM.ExtensionModel { }

                    Menu
                    {
                        id: sub_menu
                        title: model.name;
                        visible: actions != null
                        enabled: actions != null
                        Instantiator
                        {
                            model: actions
                            MenuItem
                            {
                                text: model.text
                                onTriggered: extensions.model.subMenuTriggered(name, model.text)
                            }
                            onObjectAdded: sub_menu.insertItem(index, object)
                            onObjectRemoved: sub_menu.removeItem(object)
                        }
                    }

                    onObjectAdded: extension_menu.insertItem(index, object)
                    onObjectRemoved: extension_menu.removeItem(object)
                }
            }

            Menu
            {
                id: preferencesMenu
                title: catalog.i18nc("@title:menu menubar:toplevel","P&references");

                MenuItem { action: SteSlicer.Actions.preferences; }
            }

            Menu
            {
                id: helpMenu
                title: catalog.i18nc("@title:menu menubar:toplevel","&Help");

                MenuItem { action: SteSlicer.Actions.showProfileFolder; }
                MenuItem { action: SteSlicer.Actions.documentation; }
                MenuItem { action: SteSlicer.Actions.reportBug; }
                MenuSeparator { }
                MenuItem { action: SteSlicer.Actions.about; }
            }
        }

        UM.SettingPropertyProvider
        {
            id: machineExtruderCount

            containerStack: SteSlicer.MachineManager.activeMachine
            key: "machine_extruder_count"
            watchedProperties: [ "value" ]
            storeIndex: 0
        }

        Item
        {
            id: contentItem;

            y: menu.height
            width: parent.width;
            height: parent.height - menu.height;

            Keys.forwardTo: menu

            DropArea
            {
                anchors.fill: parent;
                onDropped:
                {
                    if (drop.urls.length > 0)
                    {

                        var nonPackages = [];
                        for (var i = 0; i < drop.urls.length; i++)
                        {
                            var filename = drop.urls[i];
                            if (filename.endsWith(".curapackage"))
                            {
                                // Try to install plugin & close.
                                SteSlicerApplication.getPackageManager().installPackageViaDragAndDrop(filename);
                                packageInstallDialog.text = catalog.i18nc("@label", "This package will be installed after restarting.");
                                packageInstallDialog.icon = StandardIcon.Information;
                                packageInstallDialog.open();
                            }
                            else
                            {
                                nonPackages.push(filename);
                            }
                        }
                        openDialog.handleOpenFileUrls(nonPackages);
                    }
                }
            }

            Toolbar
            {
                id: toolbar;

                property int mouseX: base.mouseX
                property int mouseY: base.mouseY

                anchors {
                    top: topbar.bottom;
                    topMargin: UM.Theme.getSize("window_margin").height;
                    left: sidebar.right;
                    //right: parent.right;
                }
            }

            Row
            {
                id: exrudersRow

                anchors {
                    left: sidebar.right;
                    bottom: parent.bottom;
                    bottomMargin: UM.Theme.getSize("window_margin").height;
                }

                Repeater
                    {
                        id: extruders
                        width: childrenRect.width
                        height: childrenRect.height
                        property var _model: SteSlicer.ExtrudersModel { id: extrudersModel }
                        model: _model.items.length > 1 ? _model : 0
                        ExtruderButton { extruder: model }
                    }
            }

            ObjectsList
            {
                id: objectsList;
                visible: UM.Preferences.getValue("steslicer/use_multi_build_plate");
                anchors
                {
                    bottom: parent.bottom;
                    left: parent.left;
                }
            }

            Topbar
            {
                id: topbar
                anchors.left: parent.left
                //anchors.left: sidebar.right
                anchors.right: parent.right
                anchors.top: parent.top
            }

            Loader
            {
                id: sidebar

                property bool collapsed: false;
                property var initialWidth: UM.Theme.getSize("sidebar").width;

                function callExpandOrCollapse() {
                    if (collapsed) {
                        sidebar.visible = true;
                        sidebar.initialWidth = UM.Theme.getSize("sidebar").width;
                        viewportRect = Qt.rect(0.0, 0.0, 1.0, 1.0)//(base.width - sidebar.width) / base.width, 1.0);
                        expandSidebarAnimation.start();
                    } else {
                        viewportRect = Qt.rect(0, 0, 1.0, 1.0);
                        collapseSidebarAnimation.start();
                    }
                    collapsed = !collapsed;
                    UM.Preferences.setValue("steslicer/sidebar_collapsed", collapsed);
                }

                anchors
                {
                    top: topbar.bottom
                    bottom: parent.bottom
                }

                width: initialWidth
                x: 0//base.width - sidebar.width
                source: UM.Controller.activeStage.sidebarComponent

                SmoothedAnimation {
                    id: collapseSidebarAnimation
                    target: sidebar
                    properties: "x"
                    to: - sidebar.width//base.width
                    duration: 200
                }

                SmoothedAnimation {
                    id: expandSidebarAnimation
                    target: sidebar
                    properties: "x"
                    to: 0//base.width 
                    duration: 200
                }

                Component.onCompleted:
                {
                    var sidebar_collapsed = UM.Preferences.getValue("steslicer/sidebar_collapsed");

                    if (sidebar_collapsed)
                    {
                        sidebar.collapsed = true;
                        viewportRect = Qt.rect(0, 0, 1.0, 1.0)
                        collapseSidebarAnimation.start();
                    }
                }

                MouseArea
                {
                    visible: UM.Controller.activeStage.sidebarComponent != ""
                    anchors.fill: parent
                    acceptedButtons: Qt.AllButtons
                    onWheel: wheel.accepted = true
                }
            }

            DropShadow {
                    anchors.fill: sidebar
                    radius: UM.Theme.getSize("monitor_shadow_radius").width;
                    verticalOffset: UM.Theme.getSize("monitor_shadow_offset").width;
                    color: "#3F000000"; // 25% shadow
                    source: sidebar
            }

            Loader
            {
                id: main

                anchors
                {
                    top: topbar.bottom
                    bottom: parent.bottom
                    left: sidebar.right
                    right: parent.right
                }

                MouseArea
                {
                    visible: UM.Controller.activeStage.mainComponent != ""
                    anchors.fill: parent
                    acceptedButtons: Qt.AllButtons
                    onWheel: wheel.accepted = true
                }

                source: UM.Controller.activeStage.mainComponent
            }

            JobSpecs
            {
                id: jobSpecs
                visible: UM.Controller.activeStage.stageId != "STEAppStage"
                anchors
                {
                    bottom: parent.bottom;
                    //left: sidebar.right;
                    right: parent.right;
                    bottomMargin: UM.Theme.getSize("default_margin").height;
                    rightMargin: UM.Theme.getSize("default_margin").width;
                }
            }

            UM.MessageStack
            {
                anchors
                {
                    horizontalCenter: parent.horizontalCenter
                    horizontalCenterOffset: (Math.round(UM.Theme.getSize("sidebar").width / 2))
                    top: parent.verticalCenter;
                    bottom: parent.bottom;
                    bottomMargin:  UM.Theme.getSize("default_margin").height
                }
            }
        }
    }

    // Expand or collapse sidebar
    Connections
    {
        target: SteSlicer.Actions.expandSidebar
        onTriggered: sidebar.callExpandOrCollapse()
    }

    UM.PreferencesDialog
    {
        id: preferences

        Component.onCompleted:
        {
            //; Remove & re-add the general page as we want to use our own instead of uranium standard.
            removePage(0);
            insertPage(0, catalog.i18nc("@title:tab","General"), Qt.resolvedUrl("Preferences/GeneralPage.qml"));

            removePage(1);
            insertPage(1, catalog.i18nc("@title:tab","Settings"), Qt.resolvedUrl("Preferences/SettingVisibilityPage.qml"));

            insertPage(2, catalog.i18nc("@title:tab", "Printers"), Qt.resolvedUrl("Preferences/MachinesPage.qml"));

            insertPage(3, catalog.i18nc("@title:tab", "Materials"), Qt.resolvedUrl("Preferences/Materials/MaterialsPage.qml"));

            insertPage(4, catalog.i18nc("@title:tab", "Profiles"), Qt.resolvedUrl("Preferences/ProfilesPage.qml"));

            // Remove plug-ins page because we will use the shiny new plugin browser:
            removePage(5);

            //Force refresh
            setPage(0);
        }

        onVisibleChanged:
        {
            // When the dialog closes, switch to the General page.
            // This prevents us from having a heavy page like Setting Visiblity active in the background.
            setPage(0);
        }
    }

    WorkspaceSummaryDialog
    {
        id: saveWorkspaceDialog
        property var args
        onYes: UM.OutputDeviceManager.requestWriteToDevice("local_file", PrintInformation.jobName, args)
    }

    Connections
    {
        target: SteSlicer.Actions.preferences
        onTriggered: preferences.visible = true
    }

    Connections
    {
        target: SteSlicerApplication
        onShowPreferencesWindow: preferences.visible = true
    }

    MessageDialog
    {
        id: newProjectDialog
        modality: Qt.ApplicationModal
        title: catalog.i18nc("@title:window", "New project")
        text: catalog.i18nc("@info:question", "Are you sure you want to start a new project? This will clear the build plate and any unsaved settings.")
        standardButtons: StandardButton.Yes | StandardButton.No
        icon: StandardIcon.Question
        onYes:
        {
            SteSlicerApplication.deleteAll();
            SteSlicer.Actions.resetProfile.trigger();
        }
    }

    Connections
    {
        target: SteSlicer.Actions.newProject
        onTriggered:
        {
            if(Printer.platformActivity || SteSlicer.MachineManager.hasUserSettings)
            {
                newProjectDialog.visible = true
            }
        }
    }

    Connections
    {
        target: SteSlicer.Actions.addProfile
        onTriggered:
        {

            preferences.show();
            preferences.setPage(4);
            // Create a new profile after a very short delay so the preference page has time to initiate
            createProfileTimer.start();
        }
    }

    Connections
    {
        target: SteSlicer.Actions.configureMachines
        onTriggered:
        {
            preferences.visible = true;
            preferences.setPage(2);
        }
    }

    Connections
    {
        target: SteSlicer.Actions.manageProfiles
        onTriggered:
        {
            preferences.visible = true;
            preferences.setPage(4);
        }
    }

    Connections
    {
        target: SteSlicer.Actions.manageMaterials
        onTriggered:
        {
            preferences.visible = true;
            preferences.setPage(3)
        }
    }

    Connections
    {
        target: SteSlicer.Actions.configureSettingVisibility
        onTriggered:
        {
            preferences.visible = true;
            preferences.setPage(1);
            if(source && source.key)
            {
                preferences.getCurrentItem().scrollToSection(source.key);
            }
        }
    }

    UM.ExtensionModel {
        id: steslicerExtensions
    }

    // show the plugin browser dialog
    Connections
    {
        target: SteSlicer.Actions.browsePackages
        onTriggered: {
            steslicerExtensions.callExtensionMethod("Toolbox", "browsePackages")
        }
    }

    Timer
    {
        id: createProfileTimer
        repeat: false
        interval: 1

        onTriggered: preferences.getCurrentItem().createProfile()
    }

    // BlurSettings is a way to force the focus away from any of the setting items.
    // We need to do this in order to keep the bindings intact.
    Connections
    {
        target: SteSlicer.MachineManager
        onBlurSettings:
        {
            contentItem.forceActiveFocus()
        }
    }

    ContextMenu {
        id: contextMenu
    }

    onPreClosing:
    {
        close.accepted = SteSlicerApplication.getIsAllChecksPassed();
        if (!close.accepted)
        {
            SteSlicerApplication.checkAndExitApplication();
        }
    }

    MessageDialog
    {
        id: exitConfirmationDialog
        title: catalog.i18nc("@title:window", "Closing STE Slicer")
        text: catalog.i18nc("@label", "Are you sure you want to exit STE Slicer?")
        icon: StandardIcon.Question
        modality: Qt.ApplicationModal
        standardButtons: StandardButton.Yes | StandardButton.No
        onYes: SteSlicerApplication.callConfirmExitDialogCallback(true)
        onNo: SteSlicerApplication.callConfirmExitDialogCallback(false)
        onRejected: SteSlicerApplication.callConfirmExitDialogCallback(false)
        onVisibilityChanged:
        {
            if (!visible)
            {
                // reset the text to default because other modules may change the message text.
                text = catalog.i18nc("@label", "Are you sure you want to exit STE Slicer?");
            }
        }
    }

    Connections
    {
        target: SteSlicerApplication
        onShowConfirmExitDialog:
        {
            exitConfirmationDialog.text = message;
            exitConfirmationDialog.open();
        }
    }

    Connections
    {
        target: SteSlicer.Actions.quit
        onTriggered: SteSlicerApplication.checkAndExitApplication();
    }

    Connections
    {
        target: SteSlicer.Actions.toggleFullScreen
        onTriggered: base.toggleFullscreen();
    }

    FileDialog
    {
        id: openDialog;

        //: File open dialog title
        title: catalog.i18nc("@title:window","Open file(s)")
        modality: UM.Application.platform == "linux" ? Qt.NonModal : Qt.WindowModal;
        selectMultiple: true
        nameFilters: UM.MeshFileHandler.supportedReadFileTypes;
        folder: SteSlicerApplication.getDefaultPath("dialog_load_path")
        onAccepted:
        {
            // Because several implementations of the file dialog only update the folder
            // when it is explicitly set.
            var f = folder;
            folder = f;

            SteSlicerApplication.setDefaultPath("dialog_load_path", folder);

            handleOpenFileUrls(fileUrls);
        }

        // Yeah... I know... it is a mess to put all those things here.
        // There are lots of user interactions in this part of the logic, such as showing a warning dialog here and there,
        // etc. This means it will come back and forth from time to time between QML and Python. So, separating the logic
        // and view here may require more effort but make things more difficult to understand.
        function handleOpenFileUrls(fileUrlList)
        {
            // look for valid project files
            var projectFileUrlList = [];
            var hasGcode = false;
            var nonGcodeFileList = [];
            for (var i in fileUrlList)
            {
                var endsWithG = /\.g$/;
                var endsWithGcode = /\.gcode$/;
                if (endsWithG.test(fileUrlList[i]) || endsWithGcode.test(fileUrlList[i]))
                {
                    continue;
                }
                else if (SteSlicerApplication.checkIsValidProjectFile(fileUrlList[i]))
                {
                    projectFileUrlList.push(fileUrlList[i]);
                }
                nonGcodeFileList.push(fileUrlList[i]);
            }
            hasGcode = nonGcodeFileList.length < fileUrlList.length;

            // show a warning if selected multiple files together with Gcode
            var hasProjectFile = projectFileUrlList.length > 0;
            var selectedMultipleFiles = fileUrlList.length > 1;
            if (selectedMultipleFiles && hasGcode)
            {
                infoMultipleFilesWithGcodeDialog.selectedMultipleFiles = selectedMultipleFiles;
                infoMultipleFilesWithGcodeDialog.hasProjectFile = hasProjectFile;
                infoMultipleFilesWithGcodeDialog.fileUrls = nonGcodeFileList.slice();
                infoMultipleFilesWithGcodeDialog.projectFileUrlList = projectFileUrlList.slice();
                infoMultipleFilesWithGcodeDialog.open();
            }
            else
            {
                handleOpenFiles(selectedMultipleFiles, hasProjectFile, fileUrlList, projectFileUrlList);
            }
        }

        function handleOpenFiles(selectedMultipleFiles, hasProjectFile, fileUrlList, projectFileUrlList)
        {
            // we only allow opening one project file
            if (selectedMultipleFiles && hasProjectFile)
            {
                openFilesIncludingProjectsDialog.fileUrls = fileUrlList.slice();
                openFilesIncludingProjectsDialog.show();
                return;
            }

            if (hasProjectFile)
            {
                var projectFile = projectFileUrlList[0];

                // check preference
                var choice = UM.Preferences.getValue("steslicer/choice_on_open_project");
                if (choice == "open_as_project")
                {
                    openFilesIncludingProjectsDialog.loadProjectFile(projectFile);
                }
                else if (choice == "open_as_model")
                {
                    openFilesIncludingProjectsDialog.loadModelFiles([projectFile].slice());
                }
                else    // always ask
                {
                    // ask whether to open as project or as models
                    askOpenAsProjectOrModelsDialog.fileUrl = projectFile;
                    askOpenAsProjectOrModelsDialog.show();
                }
            }
            else
            {
                openFilesIncludingProjectsDialog.loadModelFiles(fileUrlList.slice());
            }
        }
    }

    MessageDialog
    {
        id: packageInstallDialog
        title: catalog.i18nc("@window:title", "Install Package");
        standardButtons: StandardButton.Ok
        modality: Qt.ApplicationModal
    }

    MessageDialog {
        id: infoMultipleFilesWithGcodeDialog
        title: catalog.i18nc("@title:window", "Open File(s)")
        icon: StandardIcon.Information
        standardButtons: StandardButton.Ok
        text: catalog.i18nc("@text:window", "We have found one or more G-Code files within the files you have selected. You can only open one G-Code file at a time. If you want to open a G-Code file, please just select only one.")

        property var selectedMultipleFiles
        property var hasProjectFile
        property var fileUrls
        property var projectFileUrlList

        onAccepted:
        {
            openDialog.handleOpenFiles(selectedMultipleFiles, hasProjectFile, fileUrls, projectFileUrlList);
        }
    }

    Connections
    {
        target: SteSlicer.Actions.open
        onTriggered: openDialog.open()
    }

    OpenFilesIncludingProjectsDialog
    {
        id: openFilesIncludingProjectsDialog
    }

    AskOpenAsProjectOrModelsDialog
    {
        id: askOpenAsProjectOrModelsDialog
    }

    Connections
    {
        target: SteSlicerApplication
        onOpenProjectFile:
        {
            askOpenAsProjectOrModelsDialog.fileUrl = project_file;
            askOpenAsProjectOrModelsDialog.show();
        }
    }

    EngineLog
    {
        id: engineLog;
    }

    Connections
    {
        target: SteSlicer.Actions.showProfileFolder
        onTriggered:
        {
            var path = UM.Resources.getPath(UM.Resources.Preferences, "");
            if(Qt.platform.os == "windows") {
                path = path.replace(/\\/g,"/");
            }
            Qt.openUrlExternally(path);
            if(Qt.platform.os == "linux") {
                Qt.openUrlExternally(UM.Resources.getPath(UM.Resources.Resources, ""));
            }
        }
    }

    AddMachineDialog
    {
        id: addMachineDialog
        onMachineAdded:
        {
            machineActionsWizard.firstRun = addMachineDialog.firstRun
            machineActionsWizard.start(id)
        }
    }

    // Dialog to handle first run machine actions
    UM.Wizard
    {
        id: machineActionsWizard;

        title: catalog.i18nc("@title:window", "Add Printer")
        property var machine;

        function start(id)
        {
            var actions = SteSlicer.MachineActionManager.getFirstStartActions(id)
            resetPages() // Remove previous pages

            for (var i = 0; i < actions.length; i++)
            {
                actions[i].displayItem.reset()
                machineActionsWizard.appendPage(actions[i].displayItem, catalog.i18nc("@title", actions[i].label));
            }

            //Only start if there are actions to perform.
            if (actions.length > 0)
            {
                machineActionsWizard.currentPage = 0;
                show()
            }
        }
    }

    MessageDialog
    {
        id: messageDialog
        modality: Qt.ApplicationModal
        onAccepted: SteSlicerApplication.messageBoxClosed(clickedButton)
        onApply: SteSlicerApplication.messageBoxClosed(clickedButton)
        onDiscard: SteSlicerApplication.messageBoxClosed(clickedButton)
        onHelp: SteSlicerApplication.messageBoxClosed(clickedButton)
        onNo: SteSlicerApplication.messageBoxClosed(clickedButton)
        onRejected: SteSlicerApplication.messageBoxClosed(clickedButton)
        onReset: SteSlicerApplication.messageBoxClosed(clickedButton)
        onYes: SteSlicerApplication.messageBoxClosed(clickedButton)
    }

    Connections
    {
        target: SteSlicerApplication
        onShowMessageBox:
        {
            messageDialog.title = title
            messageDialog.text = text
            messageDialog.informativeText = informativeText
            messageDialog.detailedText = detailedText
            messageDialog.standardButtons = buttons
            messageDialog.icon = icon
            messageDialog.visible = true
        }
    }

    DiscardOrKeepProfileChangesDialog
    {
        id: discardOrKeepProfileChangesDialog
    }

    Connections
    {
        target: SteSlicerApplication
        onShowDiscardOrKeepProfileChanges:
        {
            discardOrKeepProfileChangesDialog.show()
        }
    }

    Connections
    {
        target: SteSlicer.Actions.addMachine
        onTriggered: addMachineDialog.visible = true;
    }

    AboutDialog
    {
        id: aboutDialog
    }

    Connections
    {
        target: SteSlicer.Actions.about
        onTriggered: aboutDialog.visible = true;
    }

    Connections
    {
        target: SteSlicerApplication
        onRequestAddPrinter:
        {
            addMachineDialog.visible = true
            addMachineDialog.firstRun = false
        }
    }

    Timer
    {
        id: startupTimer;
        interval: 100;
        repeat: false;
        running: true;
        onTriggered:
        {
            if(!base.visible)
            {
                base.visible = true;
            }

            // check later if the user agreement dialog has been closed
            if (SteSlicerApplication.needToShowUserAgreement)
            {
                restart();
            }
            else if(SteSlicer.MachineManager.activeMachine == null)
            {
                addMachineDialog.open();
            }
        }
    }
}
