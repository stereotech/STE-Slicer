#!/usr/bin/env python3

import argparse
import faulthandler
import os
import sys

from UM.Platform import Platform

parser = argparse.ArgumentParser(prog = "steslicer",
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
    def get_steslicer_dir_path():
        if Platform.isWindows():
            return os.path.expanduser("~/AppData/Roaming/steslicer")
        elif Platform.isLinux():
            return os.path.expanduser("~/.local/share/steslicer")
        elif Platform.isOSX():
            return os.path.expanduser("~/Library/Logs/steslicer")

    if hasattr(sys, "frozen"):
        dirpath = get_steslicer_dir_path()
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

    from ctypes import CDLL
    from Crypto.Util import _raw_api

    def load_pycryptodome_raw_lib(name, _):
        for ext in _raw_api.extension_suffixes:
            mod_file_name = name + ext
            for path in sys.path:
                if path.endswith('.zip'):
                    continue
                mod_file_path = os.path.join(path, mod_file_name)
                if os.path.exists(mod_file_path):
                    return CDLL(mod_file_path)

        raise OSError("Cannot load native module '%s'" % name)

    _raw_api.load_pycryptodome_raw_lib = load_pycryptodome_raw_lib
    sys.modules['Crypto.Util._raw_api'] = _raw_api


if "PYTHONPATH" in os.environ.keys():                       # If PYTHONPATH is used
    PYTHONPATH = os.environ["PYTHONPATH"].split(os.pathsep) # Get the value, split it..
    PYTHONPATH.reverse()                                    # and reverse it, because we always insert at 1
    for PATH in PYTHONPATH:                                 # Now beginning with the last PATH
        PATH_real = os.path.realpath(PATH)                  # Making the the path "real"
        if PATH_real in sys.path:                           # This should always work, but keep it to be sure..
            sys.path.remove(PATH_real)
        sys.path.insert(1, PATH_real)                       # Insert it at 1 after os.curdir, which is 0.


def exceptHook(hook_type, value, traceback):
    from steslicer.CrashHandler import CrashHandler
    from steslicer.SteSlicerApplication import SteSlicerApplication
    has_started = False
    if SteSlicerApplication.Created:
        has_started = SteSlicerApplication.getInstance().started

    from PyQt5.Qt import QApplication
    if SteSlicerApplication.Created:
        _crash_handler = CrashHandler(hook_type, value, traceback, has_started)
        if SteSlicerApplication.splash is not None:
            SteSlicerApplication.splash.close()
        if not has_started:
            SteSlicerApplication.getInstance().removePostedEvents(None)
            _crash_handler.early_crash_dialog.show()
            sys.exit(SteSlicerApplication.getInstance().exec_())
        else:
            _crash_handler.show()
    else:
        application = QApplication(sys.argv)
        application.removePostedEvents(None)
        _crash_handler = CrashHandler(hook_type, value, traceback, has_started)
        if SteSlicerApplication.splash is not None:
            SteSlicerApplication.splash.close()
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
from steslicer.SteSlicerApplication import SteSlicerApplication

app = SteSlicerApplication()
app.run()
