# app/db/mongo.py
# Connexion MongoDB async via Motor.
# Stocke les documents d'analyse de repas produits par le pipeline IA.

from decimal import Decimal
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings


def _bson_safe(obj):
    """Convertit récursivement les Decimal et autres types non-BSON en types natifs."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _bson_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_bson_safe(i) for i in obj]
    return obj

_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_collection(collection_name: str):
    client = get_mongo_client()
    return client[settings.mongo_db_name][collection_name]


meal_analyses = get_collection("meal_analyses")


async def save_meal_analysis(document: dict) -> str:
    """
    Insère un document d'analyse dans la collection meal_analyses.
    Retourne l'ObjectId du document inséré sous forme de string.
    """
    result = await meal_analyses.insert_one(_bson_safe(document))
    return str(result.inserted_id)


async def get_meal_analyses_by_user(user_id: str, limit: int = 20) -> list[dict]:
    """Retourne les N dernières analyses d'un utilisateur, tri anti-chronologique."""
    cursor = meal_analyses.find(
        {"user_id": user_id},
        {"_id": 0},
    ).sort("analyzed_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def ping_mongo() -> bool:
    """Health check : vérifie que MongoDB est joignable."""
    try:
        await get_mongo_client().admin.command("ping")
        return True
    except Exception:
        return False
