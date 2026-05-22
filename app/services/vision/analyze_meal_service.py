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
    calculate_meal_totals,
    compute_meal_needs,
    compute_meal_balance,
)
from app.services.vision.huggingface_client import detect_food_with_hf


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
    user_id:     str,
    meal_type:   Literal["breakfast", "lunch", "dinner", "snack"],
    image_bytes: bytes,
    db:          AsyncSession,
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

    # ── 2. Vision IA ──────────────────────────────────────────────────────────
    try:
        raw_labels: list[dict] = await detect_food_with_hf(image_bytes)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Service vision indisponible : {exc}")

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
            ingredient["quantity_grams"] = 100   # quantité estimée par défaut
            matched_raw.append(ingredient)
        else:
            not_found.append(food_name)

    # ── 4. Calculs nutritionnels ──────────────────────────────────────────────
    meal_totals  = calculate_meal_totals(matched_raw)
    daily_needs  = compute_meal_needs(user)
    meal_balance = compute_meal_balance(meal_totals, daily_needs)

    # ── 5. Recommandation Ollama (non bloquant) ───────────────────────────────
    recommendation: str | None = None
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
                "calories":  round(float(ing["calories_g"]) * ing["quantity_grams"] / 100, 2),
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
