"""EasyPassword Backend - FastAPI Application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.modules.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = configure_logging()
    logger.info("EasyPassword API starting", extra={"app_env": settings.APP_ENV})
    yield


app = FastAPI(
    title="EasyPassword API",
    description="Passwordless vault with WebAuthn and end-to-end encryption",
    version="1.0.0",
    lifespan=lifespan,
)


register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
