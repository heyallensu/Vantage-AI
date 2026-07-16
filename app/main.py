"""
FastAPI entry point.
Registers all routers and creates DB tables on startup.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.models.record import create_tables
from app.routers.documents import router
from app.routers.insights import router_insights
from app.routers.records import router_records


def create_app(*, create_database_tables: bool = True) -> FastAPI:
    """Build the API application, optionally enabling database startup setup."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if create_database_tables:
            create_tables()
        yield

    application = FastAPI(
        title="Vantage AI API",
        description="Intelligent Document Processing Platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    application.include_router(router)
    application.include_router(router_records)
    application.include_router(router_insights)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    return application


app = create_app()
