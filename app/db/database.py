# app/db/database.py
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

# ─────────────────────────────────────────────
# Moteur async — une seule instance pour tout le processus
# ─────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=False,          # Passer à True pour voir les requêtes SQL dans les logs
    pool_pre_ping=True,  # Vérifie que la connexion est vivante avant chaque requête
    pool_size=5,         # Connexions permanentes dans le pool
    max_overflow=10,     # Connexions supplémentaires autorisées en pic de charge
)

# Fabrique de sessions async
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Les objets restent accessibles après commit
)


# ─────────────────────────────────────────────
# Dépendance FastAPI
# ─────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Fournit une session DB à chaque route FastAPI qui en a besoin.

    Usage dans une route :
        async def ma_route(db: AsyncSession = Depends(get_db)):
            ...

    - Commit automatique si la requête se termine sans erreur.
    - Rollback automatique en cas d'exception (évite les transactions orphelines).
    - La session est toujours fermée en fin de requête (bloc finally).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─────────────────────────────────────────────
# Health check (utilisé par la route /health)
# ─────────────────────────────────────────────
async def ping_db() -> bool:
    """
    Vérifie que la base de données est joignable.
    Retourne True si OK, False sinon.
    Utilisé par la route GET /health pour exposer l'état de la DB.
    """
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False