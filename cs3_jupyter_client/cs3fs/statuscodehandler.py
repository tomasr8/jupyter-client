"""
statuscodehandler.py

Authors: Rasmus Welander.
Emails: rasmus.oscar.welander@cern.ch.
"""

from cs3client.exceptions import AuthenticationException, PermissionDeniedException, NotFoundException, AlreadyExistsException, FileLockedException, UnimplementedException


class StatusCodeHandler:
    def handle_errors(self, e: Exception) -> None:

        if isinstance(e, FileLockedException):
            raise OSError("Resource temporarily unavailable")
        if isinstance(e, AlreadyExistsException):
            raise FileExistsError("File already exists")
        if isinstance(e, UnimplementedException):
            raise NotImplementedError("Operation not implemented")
        if isinstance(e, NotFoundException):
            raise FileNotFoundError("No such file or directory")
        if isinstance(e, AuthenticationException):
            raise PermissionError("Authentication failed")
        if isinstance(e, PermissionDeniedException):
            raise PermissionError("Permission denied")
        if isinstance(e, ValueError):
            raise ValueError("Invalid input")
        raise OSError(f"Unknown error occurred: {e}")

class ErrorToHttpCode:
    def map_exception_to_http_code(self, e: Exception) -> int:
        if isinstance(e, FileLockedException):
            return 423  # Locked
        if isinstance(e, AlreadyExistsException):
            return 409  # Conflict
        if isinstance(e, UnimplementedException):
            return 501  # Not Implemented
        if isinstance(e, NotFoundException):
            return 404  # Not Found
        if isinstance(e, AuthenticationException):
            return 401  # Unauthorized
        if isinstance(e, PermissionDeniedException):
            return 403  # Forbidden
        if isinstance(e, ValueError):
            return 400  # Bad Request
        return 500  # Internal Server Error
