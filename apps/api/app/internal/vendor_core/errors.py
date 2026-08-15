# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
from fastapi import Request
from fastapi.responses import JSONResponse


class BaseApplicationError(Exception):
    """Base error for all microservice applications."""

    def __init__(
        self, message: str, code: str = "INTERNAL_SERVER_ERROR", status_code: int = 500
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class DatabaseError(BaseApplicationError):
    """Raised when a database error occurs."""

    def __init__(self, message: str):
        super().__init__(message, code="DATABASE_ERROR", status_code=500)


class ConfigurationError(BaseApplicationError):
    """Raised when environment variables or application configuration is incorrect."""

    def __init__(self, message: str):
        super().__init__(message, code="CONFIGURATION_ERROR", status_code=500)


class ExternalAPIError(BaseApplicationError):
    """Raised when a call to an external API (like LLMs or GitHub) fails."""

    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(
            f"Error communicating with {provider}: {message}",
            code="EXTERNAL_API_ERROR",
            status_code=502,
        )


class ValidationError(BaseApplicationError):
    """Raised when input validation fails."""

    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400)


class NotFoundError(BaseApplicationError):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str):
        super().__init__(message, code="NOT_FOUND", status_code=404)


class ConflictError(BaseApplicationError):
    """Raised when a resource state conflict occurs (e.g. unique constraint)."""

    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT", status_code=409)


class UnauthorizedError(BaseApplicationError):
    """Raised when authentication is required and fails or is missing."""

    def __init__(self, message: str):
        super().__init__(message, code="UNAUTHORIZED", status_code=401)


class ForbiddenError(BaseApplicationError):
    """Raised when authorization fails (insufficient permissions)."""

    def __init__(self, message: str):
        super().__init__(message, code="FORBIDDEN", status_code=403)


class ExternalServiceError(BaseApplicationError):
    """Raised when an external service dependency fails."""

    def __init__(self, message: str):
        super().__init__(message, code="EXTERNAL_SERVICE_ERROR", status_code=502)


async def application_error_handler(request: Request, exc: BaseApplicationError):
    """Global handler for application exceptions to return structured JSON errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "status": exc.status_code},
    )
