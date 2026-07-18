"""FastAPI application factory and public operational endpoints."""

import logging
import re
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.security import require_api_key
from app.models.record import get_db
from app.routers.documents import router
from app.routers.insights import router_insights
from app.routers.records import router_records

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application without mutating database schema at startup."""
    resolved_settings = settings or get_settings()
    access_logger = configure_logging()
    application = FastAPI(
        title="Vantage AI API",
        description="Intelligent Document Processing Platform",
        version="1.0.0",
    )
    application.state.settings = resolved_settings
    application.dependency_overrides[get_settings] = lambda: resolved_settings

    protected = [Depends(require_api_key)]
    application.include_router(router, dependencies=protected)
    application.include_router(router_records, dependencies=protected)
    application.include_router(router_insights, dependencies=protected)

    @application.middleware("http")
    async def log_request(request: Request, call_next):
        started = time.perf_counter()
        requested_id = request.headers.get("X-Request-ID", "")
        request_id = (
            requested_id if REQUEST_ID_PATTERN.fullmatch(requested_id) else str(uuid.uuid4())
        )
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            access_logger.exception(
                "request_failed",
                extra={"route": request.url.path, "request_id": request_id},
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers={"X-Request-ID": request_id},
            )
        finally:
            fields = {
                "route": request.url.path,
                "method": request.method,
                "status": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "request_id": request_id,
            }
            document_id = _document_id_from_path(request.url.path)
            if document_id:
                fields["document_id"] = document_id
            access_logger.info("request_completed", extra=fields)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    @application.get("/ready")
    def ready(db: Session = Depends(get_db)) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logging.getLogger("vantage.access").warning("readiness_check_failed")
            raise HTTPException(status_code=503, detail="Database is not ready") from exc
        return {"status": "ready"}

    return application


def _document_id_from_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "documents" and parts[1] != "upload":
        return parts[1]
    return None


app = create_app()
