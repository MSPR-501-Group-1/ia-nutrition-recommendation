# app/models/meal_analysis.py
# Modèles Pydantic pour les requêtes API et le document MongoDB.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# SOUS-MODÈLES — Vision
# ─────────────────────────────────────────────

class DetectedLabel(BaseModel):
    label:       str
    description: Optional[str] = None
    score:       float = Field(ge=0.0, le=1.0)


class VisionResult(BaseModel):
    provider:                  str
    labels_detected:           list[DetectedLabel]
    confidence_threshold_used: float


# ─────────────────────────────────────────────
# SOUS-MODÈLES — Nutrition
# ─────────────────────────────────────────────

class IngredientMatch(BaseModel):
    ingredient_id:  str
    name:           str
    calories_g:     float
    protein_g:      float
    carbs_g:        float
    fat_g:          float
    fiber_g:        Optional[float] = None
    detected_label: str
    confidence:     float
    quantity_grams: int = 100


class MealTotals(BaseModel):
    calories:  float
    protein_g: float
    carbs_g:   float
    fat_g:     float
    fiber_g:   float


class NutritionResult(BaseModel):
    ingredients_matched:  list[IngredientMatch]
    ingredients_not_found: list[str]
    meal_totals:          MealTotals


# ─────────────────────────────────────────────
# DOCUMENT MONGODB
# ─────────────────────────────────────────────

class MealAnalysisDocument(BaseModel):
    """Structure complète du document stocké dans MongoDB."""
    user_id:           str
    meal_type:         str
    photo_url:         Optional[str] = None
    analyzed_at:       str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    vision_result:     VisionResult
    nutrition_result:  NutritionResult
    recommendation:    Optional[str] = None
    recommendation_id: Optional[str] = None


# ─────────────────────────────────────────────
# SCHÉMAS DE RÉPONSE API
# ─────────────────────────────────────────────

class MealAnalysisResponse(BaseModel):
    status:           str
    analysis_id:      str
    vision_result:    dict
    nutrition_result: dict
    daily_needs:      Optional[dict] = None
    meal_balance:     Optional[dict] = None
    recommendation:   Optional[str]  = None


class DailyNeedsResponse(BaseModel):
    status:      str
    user_id:     str
    daily_needs: dict


class IngredientSearchResponse(BaseModel):
    status:  str
    count:   int
    results: list[dict]


class MealPlanResponse(BaseModel):
    status:  str
    user_id: str
    days:    int
    plan:    dict
