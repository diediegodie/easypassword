from __future__ import annotations

from fastapi import FastAPI, Request
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


class ForbiddenError(EasyPasswordError):
    status_code = 403


class NotFoundError(EasyPasswordError):
    status_code = 404


class ConflictError(EasyPasswordError):
    status_code = 409


class ValidationError(EasyPasswordError):
    status_code = 422


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
