import webbrowser
from unittest.mock import MagicMock, patch

from UM.Preferences import Preferences
from cura.OAuth2.AuthorizationHelpers import AuthorizationHelpers
from cura.OAuth2.AuthorizationService import AuthorizationService
from cura.OAuth2.LocalAuthorizationServer import LocalAuthorizationServer
from cura.OAuth2.Models import OAuth2Settings, AuthenticationResponse, UserProfile

CALLBACK_PORT = 32118
OAUTH_ROOT = "https://account.ultimaker.com"
CLOUD_API_ROOT = "https://api.ultimaker.com"

OAUTH_SETTINGS = OAuth2Settings(
            OAUTH_SERVER_URL= OAUTH_ROOT,
            CALLBACK_PORT=CALLBACK_PORT,
            CALLBACK_URL="http://localhost:{}/callback".format(CALLBACK_PORT),
            CLIENT_ID="",
            CLIENT_SCOPES="",
            AUTH_DATA_PREFERENCE_KEY="test/auth_data",
            AUTH_SUCCESS_REDIRECT="{}/app/auth-success".format(OAUTH_ROOT),
            AUTH_FAILED_REDIRECT="{}/app/auth-error".format(OAUTH_ROOT)
        )

FAILED_AUTH_RESPONSE = AuthenticationResponse(success = False, err_message = "FAILURE!")

SUCCESFULL_AUTH_RESPONSE = AuthenticationResponse(access_token = "beep", refresh_token = "beep?")

MALFORMED_AUTH_RESPONSE = AuthenticationResponse()


def test_cleanAuthService() -> None:
    # Ensure that when setting up an AuthorizationService, no data is set.
    authorization_service = AuthorizationService(OAUTH_SETTINGS, Preferences())
    authorization_service.initialize()
    assert authorization_service.getUserProfile() is None
    assert authorization_service.getAccessToken() is None


def test_failedLogin() -> None:
    authorization_service = AuthorizationService(OAUTH_SETTINGS, Preferences())
    authorization_service.onAuthenticationError.emit = MagicMock()
    authorization_service.onAuthStateChanged.emit = MagicMock()
    authorization_service.initialize()

    # Let the service think there was a failed response
    authorization_service._onAuthStateChanged(FAILED_AUTH_RESPONSE)

    # Check that the error signal was triggered
    assert authorization_service.onAuthenticationError.emit.call_count == 1

    # Since nothing changed, this should still be 0.
    assert authorization_service.onAuthStateChanged.emit.call_count == 0

    # Validate that there is no user profile or token
    assert authorization_service.getUserProfile() is None
    assert authorization_service.getAccessToken() is None


@patch.object(AuthorizationService, "getUserProfile", return_value=UserProfile())
def test_storeAuthData(get_user_profile) -> None:
    preferences = Preferences()
    authorization_service = AuthorizationService(OAUTH_SETTINGS, preferences)
    authorization_service.initialize()

    # Write stuff to the preferences.
    authorization_service._storeAuthData(SUCCESFULL_AUTH_RESPONSE)
    preference_value = preferences.getValue(OAUTH_SETTINGS.AUTH_DATA_PREFERENCE_KEY)
    # Check that something was actually put in the preferences
    assert preference_value is not None and preference_value != {}

    # Create a second auth service, so we can load the data.
    second_auth_service = AuthorizationService(OAUTH_SETTINGS, preferences)
    second_auth_service.initialize()
    second_auth_service.loadAuthDataFromPreferences()
    assert second_auth_service.getAccessToken() == SUCCESFULL_AUTH_RESPONSE.access_token


@patch.object(LocalAuthorizationServer, "stop")
@patch.object(LocalAuthorizationServer, "start")
@patch.object(webbrowser, "open_new")
def test_localAuthServer(webbrowser_open, start_auth_server, stop_auth_server) -> None:
    preferences = Preferences()
    authorization_service = AuthorizationService(OAUTH_SETTINGS, preferences)
    authorization_service.startAuthorizationFlow()
    assert webbrowser_open.call_count == 1

    # Ensure that the Authorization service tried to start the server.
    assert start_auth_server.call_count == 1
    assert stop_auth_server.call_count == 0
    authorization_service._onAuthStateChanged(FAILED_AUTH_RESPONSE)

    # Ensure that it stopped the server.
    assert stop_auth_server.call_count == 1


def test_loginAndLogout() -> None:
    preferences = Preferences()
    authorization_service = AuthorizationService(OAUTH_SETTINGS, preferences)
    authorization_service.onAuthenticationError.emit = MagicMock()
    authorization_service.onAuthStateChanged.emit = MagicMock()
    authorization_service.initialize()

    # Let the service think there was a succesfull response
    with patch.object(AuthorizationHelpers, "parseJWT", return_value=UserProfile()):
        authorization_service._onAuthStateChanged(SUCCESFULL_AUTH_RESPONSE)

    # Ensure that the error signal was not triggered
    assert authorization_service.onAuthenticationError.emit.call_count == 0

    # Since we said that it went right this time, validate that we got a signal.
    assert authorization_service.onAuthStateChanged.emit.call_count == 1
    assert authorization_service.getUserProfile() is not None
    assert authorization_service.getAccessToken() == "beep"

    # Check that we stored the authentication data, so next time the user won't have to log in again.
    assert preferences.getValue("test/auth_data") is not None

    # We're logged in now, also check if logging out works
    authorization_service.deleteAuthData()
    assert authorization_service.onAuthStateChanged.emit.call_count == 2
    assert authorization_service.getUserProfile() is None

    # Ensure the data is gone after we logged out.
    assert preferences.getValue("test/auth_data") == "{}"


def test_wrongServerResponses() -> None:
    authorization_service = AuthorizationService(OAUTH_SETTINGS, Preferences())
    authorization_service.initialize()
    with patch.object(AuthorizationHelpers, "parseJWT", return_value=UserProfile()):
        authorization_service._onAuthStateChanged(MALFORMED_AUTH_RESPONSE)
    assert authorization_service.getUserProfile() is None
