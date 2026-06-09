import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query
from app.db import queries
from app.db import mongo as db_mongo
from app.db.database import AsyncSession, get_db
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

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# MOCK — Contrat d'API figé pour le développement front-end
# Données réalistes prêtes à l'emploi, sans dépendance Ollama ni PostgreSQL.
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_FILE = Path(__file__).parent / "mock_meal_plan.json"


@router.get(
    "/meal-plan/mock",
    response_model=MealPlanResponse,
    response_model_exclude_none=True,
    summary="[DEV] Retourne un plan de repas mocké (contrat d'API figé)",
    tags=["Nutrition IA - Mock"],
)
async def get_mock_meal_plan():
    """
    **Endpoint de développement uniquement.**

    Retourne un objet JSON conforme au contrat d'API définitif
    de `POST /users/{user_id}/meal-plan`, validé par le modèle `MealPlanResponse`.

    Le front-end peut consommer cet endpoint sans aucune dépendance
    (pas de PostgreSQL, pas d'Ollama, pas de token).
    """
    try:
        with _MOCK_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Fichier mock introuvable.")


# ─────────────────────────────────────────────────────────────────────────────
# ADAPTATEUR — Convertit la sortie brute d'Ollama vers le contrat MealPlanResponse
#
# Ollama retourne :
#   { "day_1": { "breakfast": { "name": "...", "ingredients": [...], "estimated_calories": 380 }, ... } }
#
# On normalise vers le contrat défini dans app/models/meal_plan.py.
# Les champs impossibles à calculer sans la DB (macros détaillées, coûts)
# sont laissés à None — ils seront enrichis lors de l'intégration DB complète.
# ─────────────────────────────────────────────────────────────────────────────

_EMPTY_MACROS = {
    "calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0,
    "fat_g": 0.0, "fiber_g": 0.0,
}

_MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"]


def _map_ollama_to_contract(
    user: dict,
    raw_plan: dict,
    days: int,
    request_id: str,
) -> dict:
    """
    Mappe la réponse brute d'Ollama vers le contrat MealPlanResponse.

    Limitations actuelles (TODO) :
    - target_calories_daily : hardcodé à 2000 kcal — remplacer par le calcul BMR
      (Harris-Benedict) dès que les métriques utilisateur sont disponibles.
    - macros_per_serving : à 0 — seront recalculées via JOIN recipe_ingredients × ingredient.
    - estimated_cost_eur : None — à implémenter quand la colonne `price_per_100g`
      sera ajoutée à la table `ingredient`.
    """
    allergies = user.get("allergies")
    excluded = [allergies] if allergies and allergies != "NONE" else []

    daily_plans = []
    for i in range(1, days + 1):
        day_raw = raw_plan.get(f"day_{i}", {})
        meals = []

        for meal_type in _MEAL_ORDER:
            meal_raw = day_raw.get(meal_type)
            if not meal_raw:
                continue

            # Ollama peut retourner les ingrédients comme liste de strings ou de dicts
            raw_ings = meal_raw.get("ingredients", [])
            ingredients = []
            for j, ing in enumerate(raw_ings):
                ing_name = ing if isinstance(ing, str) else ing.get("name", str(ing))
                ingredients.append({
                    "ingredient_id": f"ollama_{i}_{meal_type}_{j}",
                    "name": ing_name,
                    "category": "OTHER",
                    "quantity_g": 100.0,
                    "unit": "g",
                    "macros_per_serving": _EMPTY_MACROS.copy(),
                    # estimated_cost_eur absent → None géré par response_model_exclude_none
                })

            estimated_cal = float(meal_raw.get("estimated_calories", 0))

            recipe = {
                "recipe_id": f"ollama_day{i}_{meal_type}",
                "title": meal_raw.get("name", meal_type.capitalize()),
                "instructions": meal_raw.get(
                    "instructions",
                    "Instructions non fournies par le modèle IA."
                ),
                "ingredients": ingredients,
                "nutritional_summary": {
                    **_EMPTY_MACROS.copy(),
                    "calories": estimated_cal,
                },
                # Champs optionnels : présents si Ollama les a fournis
                "prep_time_min":  meal_raw.get("prep_time_min"),
                "cook_time_min":  meal_raw.get("cook_time_min"),
                "servings":       meal_raw.get("servings", 1),
                "tags":           meal_raw.get("tags"),
                "ai_notes":       meal_raw.get("ai_notes"),
            }
            meals.append({"meal_type": meal_type, "recipe": recipe})

        day_total_cal = sum(
            m["recipe"]["nutritional_summary"]["calories"] for m in meals
        )
        daily_plans.append({
            "day_number": i,
            "total_calories": day_total_cal,
            "total_macros": {**_EMPTY_MACROS.copy(), "calories": day_total_cal},
            "meals": meals,
        })

    return {
        "status": "success",
        "request_id": request_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_context": {
            "user_id":     user["user_id"],
            "first_name":  user.get("first_name"),
            "goal":        user.get("goal_label"),
            "diet_type":   user.get("diet_type"),
            "allergies":   excluded,
            "height_cm":   user.get("height"),
            "weight_kg":   user.get("weight"),
        },
        "plan_metadata": {
            "duration_days":           days,
            "target_calories_daily":   2000.0,   # TODO: calcul BMR Harris-Benedict
            "target_macros":           {"protein_g": 150.0, "carbs_g": 200.0, "fat_g": 65.0},
            "diet_type":               user.get("diet_type"),
            "excluded_allergens":      excluded,
        },
        "daily_plans": daily_plans,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCTION
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

    safe_foods = await queries.get_foods_filtered_by_constraints(db, user)
    raw_plan   = await nlp_generate_meal_plan(user, safe_foods, days)

    # Si Ollama a retourné une erreur, on la remonte proprement
    if "error" in raw_plan:
        raise HTTPException(
            status_code=503,
            detail=f"Service IA indisponible : {raw_plan['error']}",
        )

    request_id = str(uuid.uuid4())
    return _map_ollama_to_contract(user, raw_plan, days, request_id)


# ─────────────────────────────────────────────────────────────────────────────
#  GET /ingredients/search
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/ingredients/search",
    response_model=IngredientSearchResponse,
    response_model_exclude_none=True,
    summary="Recherche d'ingrédients dans la base nutritionnelle",
    tags=["Nutrition IA"],
    responses={
        400: {"description": "Paramètre 'q' manquant ou trop court"},
    },
)
async def search_ingredient(
    q: str = Query(..., min_length=2, description="Terme de recherche (min 2 caractères)"),
    limit: int = Query(10, ge=1, le=50, description="Nombre maximum de résultats"),
    db: AsyncSession = Depends(get_db),
):
    """
    Recherche plein-texte dans la table `ingredient` (PostgreSQL).
    Interroge les colonnes `name` et `usda_name` avec un filtre `ILIKE`.
    Résultats triés alphabétiquement, limités à `limit`.
    """
    rows = await queries.search_ingredients(db, q, limit)
    return IngredientSearchResponse(
        status="success",
        query=q,
        count=len(rows),
        results=[IngredientResult(**r) for r in rows],
    )


# ─────────────────────────────────────────────────────────────────────────────
#  GET /users/{user_id}/daily-needs
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users/{user_id}/daily-needs",
    response_model=DailyNeedsResponse,
    summary="Calcule les besoins nutritionnels journaliers de l'utilisateur",
    tags=["Nutrition IA"],
    responses={
        404: {"description": "Utilisateur introuvable"},
    },
)
async def get_daily_needs(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Calcule les besoins caloriques et macros journaliers via **Harris-Benedict révisé**.

    - `bmr_kcal` : métabolisme de base (au repos)
    - `tdee_kcal` : dépense énergétique totale (activité sédentaire ×1.2)
    - `calorie_target` : cible ajustée selon l'objectif de santé
      (-500 kcal perte de poids, +300 kcal prise de masse)
    """
    user = await queries.get_user_profile(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    # Remapping des clés pour correspondre au calculateur
    user_for_calc = {
        **user,
        "current_weight_kg": user.get("weight"),
        "height_cm":         user.get("height"),
    }
    needs = calculate_daily_needs(user_for_calc)

    return DailyNeedsResponse(
        status="success",
        user_id=user_id,
        first_name=user.get("first_name"),
        daily_needs=DailyNeedsDetail(**needs),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  GET /users/{user_id}/analyses
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users/{user_id}/analyses",
    response_model=UserAnalysesResponse,
    summary="Historique des analyses de repas de l'utilisateur",
    tags=["Nutrition IA"],
)
async def get_user_analyses(
    user_id: str,
    limit: int = Query(10, ge=1, le=50, description="Nombre maximum d'analyses à retourner"),
):
    """
    Retourne les N dernières analyses de repas de l'utilisateur, stockées dans **MongoDB**.
    Tri anti-chronologique (plus récente en premier).

    Chaque élément est un résumé compact — pour le détail complet d'une analyse,
    utiliser `POST /users/{user_id}/analyze-meal`.
    """
    docs = await db_mongo.get_meal_analyses_by_user(user_id, limit)
    summaries = [
        MealAnalysisSummary(
            analyzed_at=doc.get("analyzed_at", ""),
            meal_type=doc.get("meal_type", "unknown"),
            calories=float(
                doc.get("nutrition_result", {})
                   .get("meal_totals", {})
                   .get("calories", 0.0)
            ),
            ingredients_matched=len(
                doc.get("nutrition_result", {})
                   .get("ingredients_matched", [])
            ),
            recommendation_available=bool(doc.get("recommendation")),
        )
        for doc in docs
    ]
    return UserAnalysesResponse(
        status="success",
        user_id=user_id,
        count=len(summaries),
        analyses=summaries,
    )