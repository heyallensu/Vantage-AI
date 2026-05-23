"""
FastAPI entry point.
Registers all routers and creates DB tables on startup.
"""

from fastapi import FastAPI

from app.models.record import create_tables
from app.routers.documents import router
from app.routers.records import router_records
from app.routers.insights import router_insights

app = FastAPI(
    title       = "Vantage AI API",
    description = "Intelligent Document Processing Platform",
    version     = "1.0.0",
)

# Create DB tables on startup (idempotent — safe to call every time)
@app.on_event("startup")
def startup():
    create_tables()

# Register routers
app.include_router(router)           # /documents
app.include_router(router_records)   # /records
app.include_router(router_insights)  # /insights

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
