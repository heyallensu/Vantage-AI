"""
FastAPI entry point.
Registers all routers and creates DB tables on startup.
"""

from fastapi import FastAPI

from app.routers.documents import router
from app.routers.insights import router_insights
from app.routers.records import router_records


def create_app() -> FastAPI:
    """Build the API application without mutating database schema at startup."""
    application = FastAPI(
        title="Vantage AI API",
        description="Intelligent Document Processing Platform",
        version="1.0.0",
    )

    application.include_router(router)
    application.include_router(router_records)
    application.include_router(router_insights)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    return application


app = create_app()
