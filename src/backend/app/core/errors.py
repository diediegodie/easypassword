from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class EasyPasswordError(Exception):
    status_code = 400


class AuthError(EasyPasswordError):
    status_code = 401


class ForbiddenError(EasyPasswordError):
    status_code = 403


class NotFoundError(EasyPasswordError):
    status_code = 404


class ConflictError(EasyPasswordError):
    status_code = 409


class ValidationError(EasyPasswordError):
    status_code = 422


def _exception_handler(status_code: int):
    async def handler(_: Request, exc: EasyPasswordError) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

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
