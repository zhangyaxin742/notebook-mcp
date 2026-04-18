from __future__ import annotations

from typing import Any


class NotebookLMConnectorError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.retryable = retryable


class AuthExpiredError(NotebookLMConnectorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="auth_expired", details=details, retryable=True)


class EndpointDriftError(NotebookLMConnectorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="endpoint_drift", details=details)


class UnsupportedShapeError(NotebookLMConnectorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="unsupported_shape", details=details)


class TransportError(NotebookLMConnectorError):
    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(
            message,
            code="transport_error",
            details=details,
            retryable=retryable,
        )
