"""Errors raised by the client library."""

from __future__ import annotations


class ClientError(Exception):
    """Base class; ``str(error)`` is always a message that can be shown to a user."""


class ServerUnavailable(ClientError):
    pass


class AuthRequired(ClientError):
    pass


class ApiError(ClientError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class NoFormatError(ClientError):
    """The user has not uploaded a resume format yet."""
