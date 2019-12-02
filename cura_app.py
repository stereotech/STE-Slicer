#!/usr/bin/env python3

# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

import argparse
import faulthandler
import os
import sys

from UM.Platform import Platform

parser = argparse.ArgumentParser(prog = "cura",
                                 add_help = False)
parser.add_argument("--debug",
                    action="store_true",
                    default = False,
                    help = "Turn on the debug mode by setting this option."
                    )
parser.add_argument("--trigger-early-crash",
                    dest = "trigger_early_crash",
                    action = "store_true",
                    default = False,
                    help = "FOR TESTING ONLY. Trigger an early crash to show the crash dialog."
                    )
known_args = vars(parser.parse_known_args()[0])

if not known_args["debug"]:
    def get_cura_dir_path():
        if Platform.isWindows():
            return os.path.expanduser("~/AppData/Roaming/cura")
        elif Platform.isLinux():
            return os.path.expanduser("~/.local/share/cura")
        elif Platform.isOSX():
            return os.path.expanduser("~/Library/Logs/cura")

    if hasattr(sys, "frozen"):
        dirpath = get_cura_dir_path()
        os.makedirs(dirpath, exist_ok = True)
        sys.stdout = open(os.path.join(dirpath, "stdout.log"), "w", encoding = "utf-8")
        sys.stderr = open(os.path.join(dirpath, "stderr.log"), "w", encoding = "utf-8")


# WORKAROUND: GITHUB-88 GITHUB-385 GITHUB-612
if Platform.isLinux(): # Needed for platform.linux_distribution, which is not available on Windows and OSX
    # For Ubuntu: https://bugs.launchpad.net/ubuntu/+source/python-qt4/+bug/941826
    # The workaround is only needed on Ubuntu+NVidia drivers. Other drivers are not affected, but fine with this fix.
    try:
        import ctypes
        from ctypes.util import find_library
        libGL = find_library("GL")
        ctypes.CDLL(libGL, ctypes.RTLD_GLOBAL)
    except:
        # GLES-only systems (e.g. ARM Mali) do not have libGL, ignore error
        pass

# When frozen, i.e. installer version, don't let PYTHONPATH mess up the search path for DLLs.
if Platform.isWindows() and hasattr(sys, "frozen"):
    try:
        del os.environ["PYTHONPATH"]
    except KeyError:
        pass

# WORKAROUND: GITHUB-704 GITHUB-708
# It looks like setuptools creates a .pth file in
# the default /usr/lib which causes the default site-packages
# to be inserted into sys.path before PYTHONPATH.
# This can cause issues such as having libsip loaded from
# the system instead of the one provided with Cura, which causes
# incompatibility issues with libArcus
if "PYTHONPATH" in os.environ.keys():                       # If PYTHONPATH is used
    PYTHONPATH = os.environ["PYTHONPATH"].split(os.pathsep) # Get the value, split it..
    PYTHONPATH.reverse()                                    # and reverse it, because we always insert at 1
    for PATH in PYTHONPATH:                                 # Now beginning with the last PATH
        PATH_real = os.path.realpath(PATH)                  # Making the the path "real"
        if PATH_real in sys.path:                           # This should always work, but keep it to be sure..
            sys.path.remove(PATH_real)
        sys.path.insert(1, PATH_real)                       # Insert it at 1 after os.curdir, which is 0.


def exceptHook(hook_type, value, traceback):
    from cura.CrashHandler import CrashHandler
    from cura.CuraApplication import CuraApplication
    has_started = False
    if CuraApplication.Created:
        has_started = CuraApplication.getInstance().started

    #
    # When the exception hook is triggered, the QApplication may not have been initialized yet. In this case, we don't
    # have an QApplication to handle the event loop, which is required by the Crash Dialog.
    # The flag "CuraApplication.Created" is set to True when CuraApplication finishes its constructor call.
    #
    # Before the "started" flag is set to True, the Qt event loop has not started yet. The event loop is a blocking
    # call to the QApplication.exec_(). In this case, we need to:
    #   1. Remove all scheduled events so no more unnecessary events will be processed, such as loading the main dialog,
    #      loading the machine, etc.
    #   2. Start the Qt event loop with exec_() and show the Crash Dialog.
    #
    # If the application has finished its initialization and was running fine, and then something causes a crash,
    # we run the old routine to show the Crash Dialog.
    #
    from PyQt5.Qt import QApplication
    if CuraApplication.Created:
        _crash_handler = CrashHandler(hook_type, value, traceback, has_started)
        if CuraApplication.splash is not None:
            CuraApplication.splash.close()
        if not has_started:
            CuraApplication.getInstance().removePostedEvents(None)
            _crash_handler.early_crash_dialog.show()
            sys.exit(CuraApplication.getInstance().exec_())
        else:
            _crash_handler.show()
    else:
        application = QApplication(sys.argv)
        application.removePostedEvents(None)
        _crash_handler = CrashHandler(hook_type, value, traceback, has_started)
        # This means the QtApplication could be created and so the splash screen. Then Cura closes it
        if CuraApplication.splash is not None:
            CuraApplication.splash.close()
        _crash_handler.early_crash_dialog.show()
        sys.exit(application.exec_())


# Set exception hook to use the crash dialog handler
sys.excepthook = exceptHook
# Enable dumping traceback for all threads
faulthandler.enable(all_threads = True)

# Workaround for a race condition on certain systems where there
# is a race condition between Arcus and PyQt. Importing Arcus
# first seems to prevent Sip from going into a state where it
# tries to create PyQt objects on a non-main thread.
import Arcus #@UnusedImport
import Savitar #@UnusedImport
from cura.CuraApplication import CuraApplication

app = CuraApplication()
app.run()
