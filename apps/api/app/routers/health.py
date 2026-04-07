"""Health-check endpoints: /healthz and /readyz."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def health():
    """Liveness probe — always 200 if the process is running."""
    return {"status": "ok"}


@router.get("/readyz")
def ready(db: Session = Depends(get_db)):
    """Readiness probe — checks Postgres connectivity."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "db": "connected"}
    except Exception as exc:
        return {"status": "not_ready", "db": str(exc)}
