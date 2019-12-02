# Copyright (c) 2018 Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.
from typing import Optional, Dict, TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty

from UM.i18n import i18nCatalog
from UM.Message import Message

from cura.OAuth2.AuthorizationService import AuthorizationService
from cura.OAuth2.Models import OAuth2Settings

if TYPE_CHECKING:
    from cura.CuraApplication import CuraApplication

i18n_catalog = i18nCatalog("cura")


##  The account API provides a version-proof bridge to use Ultimaker Accounts
#
#   Usage:
#       ``from cura.API import CuraAPI
#       api = CuraAPI()
#       api.account.login()
#       api.account.logout()
#       api.account.userProfile # Who is logged in``
#
class Account(QObject):
    # Signal emitted when user logged in or out.
    loginStateChanged = pyqtSignal(bool)

    def __init__(self, application: "CuraApplication", parent = None) -> None:
        super().__init__(parent)
        self._application = application

        self._error_message = None  # type: Optional[Message]
        self._logged_in = False

        self._callback_port = 32118
        self._oauth_root = "https://account.ultimaker.com"
        self._cloud_api_root = "https://api.ultimaker.com"

        self._oauth_settings = OAuth2Settings(
            OAUTH_SERVER_URL= self._oauth_root,
            CALLBACK_PORT=self._callback_port,
            CALLBACK_URL="http://localhost:{}/callback".format(self._callback_port),
            CLIENT_ID="um---------------ultimaker_cura_drive_plugin",
            CLIENT_SCOPES="account.user.read drive.backup.read drive.backup.write packages.download packages.rating.read packages.rating.write",
            AUTH_DATA_PREFERENCE_KEY="general/ultimaker_auth_data",
            AUTH_SUCCESS_REDIRECT="{}/app/auth-success".format(self._oauth_root),
            AUTH_FAILED_REDIRECT="{}/app/auth-error".format(self._oauth_root)
        )

        self._authorization_service = AuthorizationService(self._oauth_settings)

    def initialize(self) -> None:
        self._authorization_service.initialize(self._application.getPreferences())

        self._authorization_service.onAuthStateChanged.connect(self._onLoginStateChanged)
        self._authorization_service.onAuthenticationError.connect(self._onLoginStateChanged)
        self._authorization_service.loadAuthDataFromPreferences()

    @pyqtProperty(bool, notify=loginStateChanged)
    def isLoggedIn(self) -> bool:
        return self._logged_in

    def _onLoginStateChanged(self, logged_in: bool = False, error_message: Optional[str] = None) -> None:
        if error_message:
            if self._error_message:
                self._error_message.hide()
            self._error_message = Message(error_message, title = i18n_catalog.i18nc("@info:title", "Login failed"))
            self._error_message.show()

        if self._logged_in != logged_in:
            self._logged_in = logged_in
            self.loginStateChanged.emit(logged_in)

    @pyqtSlot()
    def login(self) -> None:
        if self._logged_in:
            # Nothing to do, user already logged in.
            return
        self._authorization_service.startAuthorizationFlow()

    @pyqtProperty(str, notify=loginStateChanged)
    def userName(self):
        user_profile = self._authorization_service.getUserProfile()
        if not user_profile:
            return None
        return user_profile.username

    @pyqtProperty(str, notify = loginStateChanged)
    def profileImageUrl(self):
        user_profile = self._authorization_service.getUserProfile()
        if not user_profile:
            return None
        return user_profile.profile_image_url

    @pyqtProperty(str, notify=loginStateChanged)
    def accessToken(self) -> Optional[str]:
        return self._authorization_service.getAccessToken()

    #   Get the profile of the logged in user
    #   @returns None if no user is logged in, a dict containing user_id, username and profile_image_url
    @pyqtProperty("QVariantMap", notify = loginStateChanged)
    def userProfile(self) -> Optional[Dict[str, Optional[str]]]:
        user_profile = self._authorization_service.getUserProfile()
        if not user_profile:
            return None
        return user_profile.__dict__

    @pyqtSlot()
    def logout(self) -> None:
        if not self._logged_in:
            return  # Nothing to do, user isn't logged in.

        self._authorization_service.deleteAuthData()
