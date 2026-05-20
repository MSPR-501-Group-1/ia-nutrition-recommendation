# app/api/health.py
# Route de health check : vérifie l'état des connexions DB et MongoDB.

from fastapi import APIRouter
from app.db.database import ping_db
from app.db.mongo import ping_mongo

router = APIRouter()


@router.get("/health", tags=["System"])
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
