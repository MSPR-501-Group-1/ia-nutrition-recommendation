# app/api/routers/nutrition.py
# Déclarations de routes Nutrition IA — aucune logique métier ici.
# Logique métier répartie dans :
#   app/services/nutrition/meal_plan_adapter.py  ← adaptateur Ollama → contrat
#   app/services/nutrition/calculator_service.py ← calculs nutritionnels
#   app/db/queries.py                            ← requêtes PostgreSQL
#   app/db/mongo.py                              ← requêtes MongoDB

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import queries, mongo as db_mongo
from app.db.database import get_db
from app.models.meal_plan import MealPlanResponse
from app.models.meal_analysis import (
    DailyNeedsResponse,
    DailyNeedsDetail,
    IngredientSearchResponse,
    IngredientResult,
    UserAnalysesResponse,
    MealAnalysisSummary,
)
from app.services.nlp.nlp_orchestrator import generate_meal_plan as nlp_generate_meal_plan
from app.services.nutrition.calculator_service import calculate_daily_needs
from app.services.nutrition.meal_plan_adapter import map_ollama_to_contract

router = APIRouter()

_MOCK_FILE = Path(__file__).parent.parent / "mock_meal_plan.json"


# ─────────────────────────────────────────────────────────────────────────────
# GET /meal-plan/mock — Contrat d'API figé pour le développement front-end
# [HORS SUJET — commenté pour l'évaluation]
# ─────────────────────────────────────────────────────────────────────────────

# @router.get(
#     "/meal-plan/mock",
#     response_model=MealPlanResponse,
#     response_model_exclude_none=True,
#     summary="[DEV] Retourne un plan de repas mocké (contrat d'API figé)",
#     tags=["Nutrition IA - Mock"],
# )
# async def get_mock_meal_plan():
#     """
#     **Endpoint de développement uniquement.**
#
#     Retourne un objet JSON conforme au contrat d'API définitif
#     de `POST /users/{user_id}/meal-plan`, validé par le modèle `MealPlanResponse`.
#
#     Le front-end peut consommer cet endpoint sans aucune dépendance
#     (pas de PostgreSQL, pas d'Ollama, pas de token).
#     """
#     try:
#         with _MOCK_FILE.open(encoding="utf-8") as f:
#             return json.load(f)
#     except FileNotFoundError:
#         raise HTTPException(status_code=500, detail="Fichier mock introuvable.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /users/{user_id}/meal-plan — Génération via Ollama
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/users/{user_id}/meal-plan",
    response_model=MealPlanResponse,
    response_model_exclude_none=True,
    summary="Génère un plan de repas personnalisé via IA (Ollama)",
    tags=["Nutrition IA"],
)
async def generate_meal_plan(
    user_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """
    Génère un plan de repas sur `days` jours via Ollama.

    La réponse est conforme au contrat `MealPlanResponse`.
    Les champs `macros_per_serving` détaillés et `estimated_cost_eur`
    sont à `null` jusqu'à l'intégration complète de la DB (voir TODO dans l'adaptateur).
    """
    user = await queries.get_user_profile(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    safe_foods, budget = await asyncio.gather(
        queries.get_ingredients_for_meal_plan(db, diet_type=user.get("diet_type")),
        queries.get_user_budget(db, user_id),
    )
    raw_plan = await nlp_generate_meal_plan(user, safe_foods, days)

    if "error" in raw_plan:
        raise HTTPException(
            status_code=503,
            detail=f"Service IA indisponible : {raw_plan['error']}",
        )

    return await map_ollama_to_contract(
        user, raw_plan, days, str(uuid.uuid4()), db, budget_max_per_meal=budget
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /ingredients/search — Recherche plein-texte dans PostgreSQL
# [HORS SUJET — commenté pour l'évaluation]
# ─────────────────────────────────────────────────────────────────────────────

# @router.get(
#     "/ingredients/search",
#     response_model=IngredientSearchResponse,
#     response_model_exclude_none=True,
#     summary="Recherche d'ingrédients dans la base nutritionnelle",
#     tags=["Nutrition IA"],
#     responses={
#         400: {"description": "Paramètre 'q' manquant ou trop court"},
#     },
# )
# async def search_ingredient(
#     q: str = Query(..., min_length=2, description="Terme de recherche (min 2 caractères)"),
#     limit: int = Query(10, ge=1, le=50, description="Nombre maximum de résultats"),
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Recherche plein-texte dans la table `ingredient` (PostgreSQL).
#     Interroge les colonnes `name` et `usda_name` avec un filtre `ILIKE`.
#     Résultats triés alphabétiquement, limités à `limit`.
#     """
#     rows = await queries.search_ingredients(db, q, limit)
#     return IngredientSearchResponse(
#         status="success",
#         query=q,
#         count=len(rows),
#         results=[IngredientResult(**r) for r in rows],
#     )


# ─────────────────────────────────────────────────────────────────────────────
# GET /users/{user_id}/daily-needs — Besoins journaliers (Harris-Benedict)
# [HORS SUJET — commenté pour l'évaluation]
# ─────────────────────────────────────────────────────────────────────────────

# @router.get(
#     "/users/{user_id}/daily-needs",
#     response_model=DailyNeedsResponse,
#     summary="Calcule les besoins nutritionnels journaliers de l'utilisateur",
#     tags=["Nutrition IA"],
#     responses={
#         404: {"description": "Utilisateur introuvable"},
#     },
# )
# async def get_daily_needs(
#     user_id: str,
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Calcule les besoins caloriques et macros journaliers via **Harris-Benedict révisé**.
#
#     - `bmr_kcal` : métabolisme de base (au repos)
#     - `tdee_kcal` : dépense énergétique totale (activité sédentaire ×1.2)
#     - `calorie_target` : cible ajustée selon l'objectif de santé
#       (-500 kcal perte de poids, +300 kcal prise de masse)
#     """
#     user = await queries.get_user_profile(db, user_id)
#     if not user:
#         raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
#
#     user_for_calc = {
#         **user,
#         "current_weight_kg": user.get("weight"),
#         "height_cm":         user.get("height"),
#     }
#     needs = calculate_daily_needs(user_for_calc)
#
#     return DailyNeedsResponse(
#         status="success",
#         user_id=user_id,
#         first_name=user.get("first_name"),
#         daily_needs=DailyNeedsDetail(**needs),
#     )


# ─────────────────────────────────────────────────────────────────────────────
# GET /users/{user_id}/analyses — Historique des analyses (MongoDB)
# [HORS SUJET — commenté pour l'évaluation]
# ─────────────────────────────────────────────────────────────────────────────

# @router.get(
#     "/users/{user_id}/analyses",
#     response_model=UserAnalysesResponse,
#     summary="Historique des analyses de repas de l'utilisateur",
#     tags=["Nutrition IA"],
# )
# async def get_user_analyses(
#     user_id: str,
#     limit: int = Query(10, ge=1, le=50, description="Nombre maximum d'analyses à retourner"),
# ):
#     """
#     Retourne les N dernières analyses de repas de l'utilisateur, stockées dans **MongoDB**.
#     Tri anti-chronologique (plus récente en premier).
#
#     Chaque élément est un résumé compact — pour le détail complet d'une analyse,
#     utiliser `POST /users/{user_id}/analyze-meal`.
#     """
#     docs = await db_mongo.get_meal_analyses_by_user(user_id, limit)
#     summaries = [
#         MealAnalysisSummary(
#             analyzed_at=doc.get("analyzed_at", ""),
#             meal_type=doc.get("meal_type", "unknown"),
#             calories=float(
#                 doc.get("nutrition_result", {})
#                    .get("meal_totals", {})
#                    .get("calories", 0.0)
#             ),
#             ingredients_matched=len(
#                 doc.get("nutrition_result", {})
#                    .get("ingredients_matched", [])
#             ),
#             recommendation_available=bool(doc.get("recommendation")),
#         )
#         for doc in docs
#     ]
#     return UserAnalysesResponse(
#         status="success",
#         user_id=user_id,
#         count=len(summaries),
#         analyses=summaries,
#     )
