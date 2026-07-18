"""Small JSON logging boundary suitable for CloudWatch ingestion."""

import json
import logging
from datetime import datetime, timezone

SERVICE_NAME = "vantage-ai-api"
OPERATIONAL_FIELDS = (
    "route",
    "method",
    "status",
    "duration_ms",
    "request_id",
    "document_id",
)


class JsonFormatter(logging.Formatter):
    """Serialize an allowlist of operational fields and exclude secrets."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": SERVICE_NAME,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for field in OPERATIONAL_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging() -> logging.Logger:
    """Configure the named access logger once and return it."""
    logger = logging.getLogger("vantage.access")
    logger.disabled = False
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "_vantage_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._vantage_json = True
        logger.addHandler(handler)
    logger.propagate = True
    return logger
