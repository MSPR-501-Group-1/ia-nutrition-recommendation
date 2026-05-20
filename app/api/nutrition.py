# app/api/nutrition.py
# Routes nutrition : recherche d ingredients, analyse complete d un repas,
# besoins journaliers et generation d un plan de repas.

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries
from app.db.database import get_db
from app.db import mongo
from app.services.vision import vision_orchestrator
from app.services.nutrition import calculator_service
from app.services.nlp import nlp_orchestrator

router = APIRouter()


# ─────────────────────────────────────────────
# GET /ingredients/search
# ─────────────────────────────────────────────

@router.get("/ingredients/search", tags=["Nutrition"])
async def search_ingredient(
    name: str = Query(..., min_length=2, description="Nom ou partie du nom de l aliment"),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Cherche des ingredients dans PostgreSQL (table ingredient).
    Recherche insensible a la casse par correspondance partielle.
    """
    results = await queries.search_ingredients(db, name, limit=limit)
    return {"status": "success", "count": len(results), "results": results}


# ─────────────────────────────────────────────
# GET /users/{user_id}/daily-needs
# ─────────────────────────────────────────────

@router.get("/users/{user_id}/daily-needs", tags=["Nutrition"])
async def get_daily_needs(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Calcule les besoins journaliers (TDEE, macros cibles) a partir
    du profil utilisateur et de la formule Harris-Benedict revisee.
    """
    user = await queries.get_user_profile(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    daily_needs = calculator_service.calculate_daily_needs(user)
    return {"status": "success", "user_id": user_id, "daily_needs": daily_needs}


# ─────────────────────────────────────────────
# POST /users/{user_id}/analyze-meal
# ─────────────────────────────────────────────

@router.post("/users/{user_id}/analyze-meal", tags=["Nutrition"])
async def analyze_meal(
    user_id: str,
    file: UploadFile = File(...),
    meal_type: str = Query(
        default="lunch",
        description="Type de repas : breakfast, lunch, dinner, snack",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Pipeline complet d analyse d un repas photo :
    1. Vision IA (HuggingFace Kimi-K2.5) -> detection des aliments
    2. Matching des labels avec la table ingredient (PostgreSQL)
    3. Calcul des macros du repas vs besoins journaliers de l utilisateur
    4. Generation d une recommandation personnalisee (Ollama)
    5. Sauvegarde du document d analyse dans MongoDB
    Retourne le bilan complet + la recommandation.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit etre une image.")

    # 1. Profil utilisateur
    user = await queries.get_user_profile(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    # 2. Vision + matching PostgreSQL
    image_bytes = await file.read()
    analysis = await vision_orchestrator.analyze_image_and_match_ingredients(
        image_bytes, db
    )

    # 3. Calculs nutritionnels
    meal_totals  = calculator_service.calculate_meal_totals(analysis["ingredients_matched"])
    daily_needs  = calculator_service.calculate_daily_needs(user)
    meal_balance = calculator_service.calculate_meal_balance(meal_totals, daily_needs)

    # 4. Recommandation NLP
    recommendation = await nlp_orchestrator.generate_meal_recommendation(
        user, meal_totals, daily_needs
    )

    # 5. Sauvegarde MongoDB
    document = {
        "user_id":      user_id,
        "meal_type":    meal_type,
        "photo_url":    None,
        "analyzed_at":  datetime.now(timezone.utc).isoformat(),
        "vision_result": {
            "provider":                  analysis["provider"],
            "labels_detected":           analysis["labels_detected"],
            "confidence_threshold_used": analysis["confidence_threshold_used"],
        },
        "nutrition_result": {
            "ingredients_matched":   analysis["ingredients_matched"],
            "ingredients_not_found": analysis["ingredients_not_found"],
            "meal_totals":           meal_totals,
        },
        "recommendation": recommendation,
    }
    analysis_id = await mongo.save_meal_analysis(document)

    return {
        "status":           "success",
        "analysis_id":      analysis_id,
        "vision_result":    document["vision_result"],
        "nutrition_result": document["nutrition_result"],
        "daily_needs":      daily_needs,
        "meal_balance":     meal_balance,
        "recommendation":   recommendation,
    }


# ─────────────────────────────────────────────
# POST /users/{user_id}/meal-plan
# ─────────────────────────────────────────────

@router.post("/users/{user_id}/meal-plan", tags=["Nutrition"])
async def generate_meal_plan(
    user_id: str,
    days: int = Query(default=7, ge=1, le=30, description="Nombre de jours du plan"),
    db: AsyncSession = Depends(get_db),
):
    """
    Genere un plan de repas sur N jours via Ollama (mistral par defaut).
    Les ingredients proposes respectent le diet_type de l utilisateur
    (vegan, vegetarian, standard…).
    """
    user = await queries.get_user_profile(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    available_ingredients = await queries.get_ingredients_for_meal_plan(
        db,
        diet_type=user.get("diet_type"),
        limit=50,
    )

    plan = await nlp_orchestrator.generate_meal_plan(user, available_ingredients, days)

    return {
        "status":  "success",
        "user_id": user_id,
        "days":    days,
        "plan":    plan,
    }


# ─────────────────────────────────────────────
# GET /users/{user_id}/analyses
# ─────────────────────────────────────────────

@router.get("/users/{user_id}/analyses", tags=["Nutrition"])
async def get_user_analyses(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Retourne les N dernieres analyses de repas de l utilisateur (depuis MongoDB).
    """
    analyses = await mongo.get_meal_analyses_by_user(user_id, limit=limit)
    return {"status": "success", "user_id": user_id, "count": len(analyses), "analyses": analyses}
