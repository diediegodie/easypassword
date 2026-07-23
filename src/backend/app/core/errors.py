from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None


class EasyPasswordError(Exception):
    status_code = 400

    def __init__(self, detail: str | None = None, code: str | None = None):
        self.detail = detail or ""
        self.code = code
        super().__init__(self.detail)


class AuthError(EasyPasswordError):
    status_code = 401


class ReauthenticationRequiredError(AuthError):
    def __init__(self, detail: str = "Session expired due to inactivity") -> None:
        super().__init__(detail=detail, code="ReauthenticationRequired")


class ERR_UNAUTHORIZED(AuthError):
    def __init__(self) -> None:
        super().__init__(
            detail="Token is invalid, missing, expired, or lacks required scope.",
            code="ERR_UNAUTHORIZED",
        )


class ERR_INVALID_TOKEN(AuthError):
    def __init__(self) -> None:
        super().__init__(
            detail="Token format is invalid or malformed.",
            code="ERR_INVALID_TOKEN",
        )


class ForbiddenError(EasyPasswordError):
    status_code = 403


class ERR_TOKEN_REVOKED(ForbiddenError):
    def __init__(self) -> None:
        super().__init__(
            detail="Token has been revoked.",
            code="ERR_TOKEN_REVOKED",
        )


class NotFoundError(EasyPasswordError):
    status_code = 404


class ConflictError(EasyPasswordError):
    status_code = 409


class ValidationError(EasyPasswordError):
    status_code = 422


class PayloadTooLargeError(EasyPasswordError):
    status_code = 413


class ReplayDetectedError(EasyPasswordError):
    status_code = 400


from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def request_validation_exception_handler(
    _: Request | WebSocket, exc: Exception
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc

    errors = exc.errors()
    if any(error.get("type") == "value_error.extra" for error in errors):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "payload contains fields not allowed",
                "code": "ERR_EXTRA_FIELDS",
            },
        )

    if any("suspicious key field" in error.get("msg", "").lower() for error in errors):
        return JSONResponse(
            status_code=400,
            content={
                "detail": "payload contains key-like fields",
                "code": "ERR_SUSPICIOUS_KEY",
            },
        )

    if any(
        "malformed or non-base64 blob" in error.get("msg", "").lower()
        for error in errors
    ):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "malformed or non-base64 blob",
                "code": "ERR_INVALID_BLOB",
            },
        )

    if any(
        "decoded blob exceeds hard limit" in error.get("msg", "").lower()
        for error in errors
    ):
        return JSONResponse(
            status_code=413,
            content={
                "detail": "decoded blob exceeds hard limit",
                "code": "ERR_BLOB_TOO_LARGE",
            },
        )

    if any(
        "duplicate blob detected within replay window" in error.get("msg", "").lower()
        for error in errors
    ):
        return JSONResponse(
            status_code=400,
            content={
                "detail": "duplicate blob detected within replay window",
                "code": "ERR_REPLAY_DETECTED",
            },
        )

    if any(
        "blob version not supported" in error.get("msg", "").lower() for error in errors
    ):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "blob version not supported",
                "code": "ERR_UNSUPPORTED_BLOB_VERSION",
            },
        )

    return JSONResponse(
        status_code=422,
        content={"detail": "validation error", "code": "ERR_INVALID_BLOB"},
    )


def _exception_handler(status_code: int):
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, EasyPasswordError):
            content = {"detail": exc.detail}
            code = getattr(exc, "code", None)
            if code is not None:
                content["code"] = code
        else:
            content = {"detail": str(exc)}
        return JSONResponse(status_code=status_code, content=content)

    return handler


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        EasyPasswordError, _exception_handler(EasyPasswordError.status_code)
    )
    app.add_exception_handler(AuthError, _exception_handler(AuthError.status_code))
    app.add_exception_handler(
        ForbiddenError, _exception_handler(ForbiddenError.status_code)
    )
    app.add_exception_handler(
        NotFoundError, _exception_handler(NotFoundError.status_code)
    )
    app.add_exception_handler(
        ConflictError, _exception_handler(ConflictError.status_code)
    )
    app.add_exception_handler(
        ValidationError, _exception_handler(ValidationError.status_code)
    )
    app.add_exception_handler(
        PayloadTooLargeError, _exception_handler(PayloadTooLargeError.status_code)
    )
    app.add_exception_handler(
        ReplayDetectedError, _exception_handler(ReplayDetectedError.status_code)
    )
    app.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
