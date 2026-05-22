# app/api/health.py
# Route de health check : vérifie l'état des connexions DB et MongoDB.

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.database import ping_db
from app.db.mongo import ping_mongo

router = APIRouter()


class _ServiceStatus(BaseModel):
    api:        Literal["ok"]
    postgresql: Literal["ok", "unreachable"]
    mongodb:    Literal["ok", "unreachable"]


class HealthResponse(BaseModel):
    status:   Literal["ok", "degraded"]
    services: _ServiceStatus


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Retourne l'état de l'API et de ses dépendances (PostgreSQL, MongoDB).
    Utilisé par Docker, Kubernetes et les outils de monitoring.
    """
    postgres_ok = await ping_db()
    mongo_ok    = await ping_mongo()

    overall = "ok" if (postgres_ok and mongo_ok) else "degraded"

    return {
        "status":    overall,
        "services": {
            "api":        "ok",
            "postgresql": "ok" if postgres_ok else "unreachable",
            "mongodb":    "ok" if mongo_ok    else "unreachable",
        },
    }
