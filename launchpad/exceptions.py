
from sanic import SanicException
from typing import Optional


class LaunchpadException(SanicException):
    pass

class NotImplemented(LaunchpadException):
    message = """Not implemented"""
    status = 501
    def __init__(self) -> None:
        super().__init__(self.message)



class LaunchpadKeyError(LaunchpadException):
    status = 500
    def __init__(self, message: str | None = None) -> None:
        super().__init__(message)

class LaunchpadValueError(LaunchpadException):
    status = 500
    def __init__(self, message: str | None = None) -> None:
        super().__init__(message)

class LaunchpadTypeError(LaunchpadException):
    status = 500
    def __init__(self, message: str | None = None) -> None:
        super().__init__(message)

class SettingsError(LaunchpadException):
    status = 500
    def __init__(self, message: str | None = None) -> None:
        super().__init__(message)

class MissingImportError(LaunchpadException):
    status = 500
    def __init__(self, message: str | None = None) -> None:
        super().__init__(message)

# -- AUTHENTICATOR ERRORS
class OutatedAuthorizationToken(LaunchpadException):
    message = """Authorization token is outdated."""
    status = 401
    def __init__(self) -> None:
        super().__init__(self.message)

class AuthorizationTokenRequired(LaunchpadException):
    message = """This endpoint is protected. Get an authorization token from `/login` endpoint."""
    status = 401
    def __init__(self) -> None:
        super().__init__(self.message)

class InvalidToken(LaunchpadException):
    message = """Invalid authorization token"""
    status = 401
    def __init__(self) -> None:
        super().__init__(self.message)

class MissingLogin(LaunchpadException):
    message = """You must provide a username and a password"""
    status = 401
    def __init__(self) -> None:
        super().__init__(self.message)

class InvalidLogin(LaunchpadException):
    message = """Invalid username or password"""
    status = 401
    def __init__(self) -> None:
        super().__init__(self.message)

class AccessDenied(LaunchpadException):
    message = """Access denied"""
    status = 401
    def __init__(self) -> None:
        super().__init__(self.message)
