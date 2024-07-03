
from sanic import SanicException

class LaunchpadException(SanicException):
    pass


# -- AUTHENTICATOR ERRORS
class OutatedAuthorizationToken(LaunchpadException):
    pass

class AuthorizationTokenRequired(LaunchpadException):
    pass

class InvalidToken(LaunchpadException):
    pass
    
class MissingLogin(LaunchpadException):
    pass
    
class InvalidLogin(LaunchpadException):
    pass

class AccessDenied(LaunchpadException):
    pass