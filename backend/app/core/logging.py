"""JSON log lines with a request id, so API calls and audit events can be correlated."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar = contextvars.ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            data["request_id"] = rid
        for key in ("method", "path", "status", "duration_ms", "user"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_modelguard", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._modelguard = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel("WARNING")
