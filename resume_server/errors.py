"""Domain errors raised by the services; the API maps them to HTTP status codes."""

from __future__ import annotations


class ServiceError(Exception):
    status_code = 400


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class UnauthorizedError(ServiceError):
    status_code = 401


class ValidationFailed(ServiceError):
    status_code = 422
