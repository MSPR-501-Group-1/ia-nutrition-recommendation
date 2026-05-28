# app/services/vision/analyze_meal_service.py
# Pipeline complet d'analyse de repas par photo.
#
# Étapes :
#   1. Profil utilisateur (PostgreSQL)
#   2. Détection des aliments via HuggingFace
#   3. Filtering par seuil de confiance (≥ CONFIDENCE_THRESHOLD)
#   4. Matching dans PostgreSQL → macros
#   5. Calculs nutritionnels (Mifflin-St Jeor)
#   6. Recommandation Ollama (non bloquant)
#   7. Persistance MongoDB + trace PostgreSQL
#   8. Construction de la réponse

from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import mongo, queries
from app.services.nlp.nlp_orchestrator import generate_meal_recommendation
from app.services.nutrition.calculator_service import (
    CONFIDENCE_THRESHOLD,
    _reliable_calories,
    calculate_meal_totals,
    compute_meal_needs,
    compute_meal_balance,
)
from app.services.vision.huggingface_client import detect_food_with_hf


# Portions typiques par catégorie DB (g par ingrédient dans un plat)
# Basées sur les recommandations ANSES / portions culinaires françaises standard
_CATEGORY_PORTIONS: dict[str, float] = {
    "MEAT":      150.0,  # viande, poisson, œufs (portion protéine standard)
    "DAIRY":      40.0,  # fromage, crème (accompagnement / garniture)
    "VEGETABLE": 120.0,  # légumes cuits ou crus
    "FRUIT":     100.0,  # fruit frais
    "GRAIN":     180.0,  # riz, pâtes, pain (cuits)
    "BEVERAGE":  200.0,  # boisson
    "SNACK":      30.0,  # noix, snack
    "OTHER":     100.0,  # défaut
}

# Mots-clés pour détecter garnitures/épices indépendamment de la catégorie DB
_GARNISH_KW = {
    "basil", "basilic", "parsley", "persil", "thyme", "thym", "oregano", "origan",
    "mint", "menthe", "tarragon", "estragon", "chive", "ciboulette", "rosemary",
    "romarin", "cilantro", "coriandre", "dill", "aneth", "sage", "sauge",
    "chervil", "cerfeuil",
}
_SAUCE_KW = {
    "sauce", "ketchup", "mayonnaise", "vinaigrette", "mustard", "moutarde",
    "gravy", "coulis", "dressing", "oil", "huile", "beurre", "butter",
}
_SPICE_KW = {
    "salt", "sel", "pepper", "poivre", "spice", "épice", "piment",
    "ginger", "gingembre", "cumin", "paprika", "curry", "cinnamon", "cannelle",
    "nutmeg", "muscade", "clove", "girofle", "anise", "anis",
}


def _estimate_portion(label: str, category: str | None) -> float:
    """
    Estime un poids réaliste pour un ingrédient détecté.

    Priorité :
      1. Garnitures / herbes → 10 g
      2. Sauces / condiments → 60 g
      3. Épices              → 5 g
      4. Catégorie DB        → portion typique ANSES
    """
    lbl = label.lower()
    if any(k in lbl for k in _GARNISH_KW):
        return 10.0
    if any(k in lbl for k in _SAUCE_KW):
        return 60.0
    if any(k in lbl for k in _SPICE_KW):
        return 5.0
    return _CATEGORY_PORTIONS.get((category or "OTHER").upper(), 100.0)


async def run_analyze_food(image_bytes: bytes, filename: str | None) -> dict:
    """
    Vision brute : détecte les aliments sans calcul de macros.
    Retourne un dict conforme à AnalyzeFoodResponse.
    """
    try:
        predictions = await detect_food_with_hf(image_bytes)
        return {
            "status":         "success",
            "filename":       filename,
            "ai_predictions": predictions,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


async def run_analyze_meal(
    user_id:            str,
    meal_type:          Literal["breakfast", "lunch", "dinner", "snack"],
    images:             list[bytes],
    db:                 AsyncSession,
    portion_grams:      int = 100,
    with_recommendation: bool = True,
) -> dict:
    """
    Pipeline complet : photo → identification → macros → recommandation IA.
    Retourne un dict conforme à AnalyzeMealResponse.

    Lève HTTPException pour :
      - 404 : utilisateur introuvable
      - 502 : service vision HuggingFace indisponible
      - 503 : erreur de persistance MongoDB
    """
    # ── 1. Profil utilisateur ─────────────────────────────────────────────────
    user = await queries.get_user_profile(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    # ── 2. Vision IA — détection sur chaque photo, fusion des labels ─────────────
    raw_labels: list[dict] = []
    try:
        for img in images:
            raw_labels += await detect_food_with_hf(img)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Service vision indisponible : {exc}")

    # Dédoublonnage : si même label détecté sur plusieurs photos, on garde la confiance max
    seen: dict[str, dict] = {}
    for lbl in raw_labels:
        key = lbl.get("label", "").lower()
        if key not in seen or lbl.get("score", 0) > seen[key].get("score", 0):
            seen[key] = lbl
    raw_labels = list(seen.values())

    confident_labels = [
        lbl for lbl in raw_labels
        if float(lbl.get("score", 0)) >= CONFIDENCE_THRESHOLD
    ]

    # ── 3. Matching PostgreSQL ────────────────────────────────────────────────
    matched_raw: list[dict] = []
    not_found:   list[str]  = []

    for lbl in confident_labels:
        food_name  = lbl.get("label", "")
        ingredient = await queries.get_ingredient_by_name(db, food_name)
        if ingredient:
            ingredient["detected_label"] = food_name
            ingredient["confidence"]     = float(lbl.get("score", 0))
            ingredient["quantity_grams"] = _estimate_portion(food_name, ingredient.get("category"))
            matched_raw.append(ingredient)
        else:
            not_found.append(food_name)

    # ── 4. Calculs nutritionnels ──────────────────────────────────────────────
    meal_totals  = calculate_meal_totals(matched_raw)
    daily_needs  = compute_meal_needs(user)
    meal_balance = compute_meal_balance(meal_totals, daily_needs)

    # ── 5. Recommandation Ollama (non bloquant) ───────────────────────────────
    recommendation: str | None = None
    if with_recommendation:
        try:
            recommendation = await generate_meal_recommendation(user, meal_totals, daily_needs)
        except Exception:
            pass  # L'analyse reste valide sans recommandation

    # ── 6. Persistance MongoDB ────────────────────────────────────────────────
    analyzed_at = datetime.now(timezone.utc).isoformat()
    try:
        mongo_doc = {
            "user_id":    user_id,
            "meal_type":  meal_type,
            "analyzed_at": analyzed_at,
            "vision_result": {
                "provider":                  "huggingface",
                "labels_detected":           raw_labels,
                "confidence_threshold_used": CONFIDENCE_THRESHOLD,
            },
            "nutrition_result": {
                "ingredients_matched":   matched_raw,
                "ingredients_not_found": not_found,
                "meal_totals":           meal_totals,
            },
            "daily_needs":    daily_needs,
            "meal_balance":   meal_balance,
            "recommendation": recommendation,
        }
        analysis_id = await mongo.save_meal_analysis(mongo_doc)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Erreur persistance MongoDB : {exc}")

    # ── 7. Trace PostgreSQL (non bloquant) ────────────────────────────────────
    try:
        await queries.save_meal_to_postgres(
            db, user_id, int(meal_totals["calories"]), meal_totals
        )
    except Exception:
        pass  # Non bloquant : le document MongoDB est déjà persisté

    # ── 8. Construction de la réponse ─────────────────────────────────────────
    matched_for_response = [
        {
            "ingredient_id":  ing["ingredient_id"],
            "name":           ing["name"],
            "detected_label": ing["detected_label"],
            "confidence":     ing["confidence"],
            "quantity_grams": ing["quantity_grams"],
            "macros": {
                "calories":  round(_reliable_calories(ing) * ing["quantity_grams"] / 100, 2),
                "protein_g": round(float(ing["protein_g"])  * ing["quantity_grams"] / 100, 2),
                "carbs_g":   round(float(ing["carbs_g"])    * ing["quantity_grams"] / 100, 2),
                "fat_g":     round(float(ing["fat_g"])      * ing["quantity_grams"] / 100, 2),
                "fiber_g":   round(float(ing["fiber_g"])    * ing["quantity_grams"] / 100, 2),
            },
        }
        for ing in matched_raw
    ]

    return {
        "status":      "success",
        "analysis_id": analysis_id,
        "analyzed_at": analyzed_at,
        "meal_type":   meal_type,
        "vision": {
            "provider":                  "huggingface",
            "labels_detected":           raw_labels,
            "confidence_threshold_used": CONFIDENCE_THRESHOLD,
            "labels_count":              len(raw_labels),
        },
        "nutrition": {
            "ingredients_matched":   matched_for_response,
            "ingredients_not_found": not_found,
            "meal_totals":           meal_totals,
        },
        "daily_needs":    daily_needs,
        "meal_balance":   meal_balance,
        "recommendation": recommendation,
    }
