from __future__ import annotations

import json
import logging as std_logging
from datetime import datetime, timezone

from app.core.config import settings


class JsonFormatter(std_logging.Formatter):
    def format(self, record: std_logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        app_env = getattr(record, "app_env", None)
        if app_env is not None:
            payload["app_env"] = app_env
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> std_logging.Logger:
    level = std_logging.DEBUG if settings.DEBUG else std_logging.INFO
    root_logger = std_logging.getLogger()
    root_logger.setLevel(level)

    handler = None
    for existing_handler in root_logger.handlers:
        if isinstance(existing_handler, std_logging.StreamHandler):
            handler = existing_handler
            break

    if handler is None:
        handler = std_logging.StreamHandler()
        root_logger.addHandler(handler)

    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())

    app_logger = std_logging.getLogger("easypassword")
    app_logger.setLevel(level)
    return app_logger
