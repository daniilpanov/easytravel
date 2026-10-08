"""EasyTravel backend: health + chat history (single-user in MVP-1)."""

from __future__ import annotations

from fastapi import FastAPI

from .models import Base, DATABASE_URL
from .policy import allowed_domains

app = FastAPI(title="EasyTravel API")


@app.on_event("startup")
def _create_tables() -> None:
    from sqlalchemy import create_engine

    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "services": {"api": "up", "db": "configured"},
        "allowlist_version": len(allowed_domains()),
    }
