
import os
from io import BytesIO
from typing import Optional

from UM.Resources import Resources
from truepy import License, LicenseData

from PyQt5.QtCore import QObject, pyqtSlot, pyqtProperty, pyqtSignal

from UM.Extension import Extension
from UM.Logger import Logger


class Licensing(QObject, Extension):
    licenseKeyChanged = pyqtSignal()

    def __init__(self, application):
        super(Licensing, self).__init__()
        self._application = application
        self._license_window = None
        self._license_context = None
        self._application.engineCreatedSignal.connect(self._onEngineCreated)
        self._application.getPreferences().addPreference("general/license_show_window", True)
        self._application.getPreferences().addPreference("general/license_key", "")
        self.licenseKeyChanged.connect(self._onLicenseKeyChanged)

    def _onLicenseKeyChanged(self):
        self.licenseValid = self._keyIsValid()

    def _keyIsValid(self) -> bool:
        try:
            path = os.path.join(Resources.getPath(self._application.ResourceTypes.Certificates), "license_cert.pem")
            with open(path, 'rb') as f:
                certificate = f.read()
            key = BytesIO(bytes.fromhex(self.licenseKey))
            lic = License.load(key, b'StereotechSTESlicerProFeatures')
            lic.verify(certificate)
            return True
        except License.InvalidSignatureException:
            Logger.log("w", "License key is wrong!")
            return False
        except FileNotFoundError:
            Logger.log("w", "Certificate not found!")
            return False
        except Exception as e:
            Logger.log("w", "License error: %s", str(e))
            return False

    def _onEngineCreated(self):
        if self._application.getPreferences().getValue("general/license_show_window"):
            self.showLicenseWindow()

    def showLicenseWindow(self):
        if not self._license_window:
            self.createLicenseWindow()
        self._license_window.show()

    @pyqtSlot(bool)
    def enterLater(self, user_choice):
        if user_choice:
            Logger.log("i", "User will enter key later")
            self._application.getPreferences().setValue("general/license_show_window", False)
            self._license_window.hide()
            self._application.setNeedToShowLicense(False)

    def setLicenseKey(self, value: str = ""):
        self._application.getPreferences().setValue("general/license_key", value)

    @pyqtProperty(str, fset = setLicenseKey, notify = licenseKeyChanged)
    def licenseKey(self) -> str:
        return self._application.getPreferences().getValue("general/license_key")

    @pyqtProperty(bool)
    def licenseValid(self):
        return self._keyIsValid()

    def createLicenseWindow(self):
        path = os.path.join(Resources.getPath(self._application.ResourceTypes.QmlFiles), "LicenseWindow.qml")
        self._license_window = self._application.createQmlComponent(path, {"manager": self})
