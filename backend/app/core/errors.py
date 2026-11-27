"""Domain errors mapped to one JSON error envelope by the API layer."""
from __future__ import annotations

from typing import Any, Optional


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class WorkflowError(DomainError):
    status_code = 422
    code = "workflow_rule"


class Unauthorized(DomainError):
    status_code = 401
    code = "unauthorized"
