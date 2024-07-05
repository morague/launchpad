
from sanic import SanicException

class LaunchpadException(SanicException):
    pass


class NotImplemented(LaunchpadException):
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