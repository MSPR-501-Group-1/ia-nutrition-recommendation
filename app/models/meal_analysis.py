# app/models/meal_analysis.py
# Contrat d'API définitif — Analyse de repas par photo (pipeline vision IA)
#
# Route cible : POST /api/v1/users/{user_id}/analyze-meal
#
# Légende :
#   - Champ sans Optional  → OBLIGATOIRE (required)
#   - Champ avec Optional  → OPTIONNEL (nullable, peut être absent)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Vision (partagés avec vision_orchestrator)
# ─────────────────────────────────────────────────────────────────────────────

class DetectedLabel(BaseModel):
    label:       str
    description: Optional[str] = None
    score:       float = Field(ge=0.0, le=1.0)


class VisionResult(BaseModel):
    """Résultat brut du modèle vision — utilisé aussi dans MealAnalysisDocument (MongoDB)."""
    provider:                  str
    labels_detected:           list[DetectedLabel]
    confidence_threshold_used: float


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Nutrition (internes, utilisés pour MongoDB et les calculs)
# ─────────────────────────────────────────────────────────────────────────────

class IngredientMatch(BaseModel):
    """Ingrédient matché dans PostgreSQL — utilisé dans MealAnalysisDocument."""
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
    ingredients_matched:   list[IngredientMatch]
    ingredients_not_found: list[str]
    meal_totals:           MealTotals


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT MONGODB — structure persistée dans la collection `meal_analyses`
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API — POST /analyze-food  (vision brute, sans calcul de macros)
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeFoodResponse(BaseModel):
    """Réponse de POST /analyze-food — liste brute des aliments détectés."""
    status:         Literal["success"]
    filename:       Optional[str] = None
    ai_predictions: list[DetectedLabel]


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API DÉFINITIF — POST /users/{user_id}/analyze-meal
# ─────────────────────────────────────────────────────────────────────────────

class MacroBreakdown(BaseModel):
    """
    Valeurs nutritionnelles pour la quantité réellement servie (pas pour 100g).
    Toutes les valeurs sont en grammes sauf `calories` (kcal).
    """
    calories:  float
    protein_g: float
    carbs_g:   float
    fat_g:     float
    fiber_g:   float


class MatchedIngredientDetail(BaseModel):
    """
    Ingrédient identifié par la vision IA ET matché dans PostgreSQL.
    Les macros sont déjà calculées pour la `quantity_grams` servie.
    """
    ingredient_id:  str
    name:           str
    detected_label: str             # label brut retourné par HuggingFace
    confidence:     float = Field(ge=0.0, le=1.0)
    quantity_grams: int   = Field(default=100, ge=1)
    macros:         MacroBreakdown  # macros pour quantity_grams (pas pour 100g)


class VisionSummary(BaseModel):
    """Résumé de l'étape vision — ce que l'IA a vu dans la photo."""
    provider:                  str            # "huggingface"
    labels_detected:           list[DetectedLabel]
    confidence_threshold_used: float
    labels_count:              int


class NutritionSummary(BaseModel):
    """Résultat de l'étape nutrition — ce qui a été matché dans la DB."""
    ingredients_matched:   list[MatchedIngredientDetail]
    ingredients_not_found: list[str]    # labels détectés mais absents de la DB
    meal_totals:           MacroBreakdown


class DailyNeeds(BaseModel):
    """
    Besoins journaliers estimés via Mifflin-St Jeor.
    `method` indique la formule et les hypothèses utilisées.
    """
    calorie_target:   float
    protein_target_g: float
    carbs_target_g:   float
    fat_target_g:     float
    method:           str   # ex: "mifflin_fat_loss" | "mifflin_general" | "default_2000kcal"


class MealBalance(BaseModel):
    """
    Pourcentage de la cible journalière couvert par ce repas.
    `assessment` : "light" < 15% < "balanced" < 50% < "heavy"
    """
    calories_pct: float
    protein_pct:  float
    carbs_pct:    float
    fat_pct:      float
    assessment:   Literal["light", "balanced", "heavy"]


class AnalyzeMealResponse(BaseModel):
    """
    Contrat d'API définitif — POST /api/v1/users/{user_id}/analyze-meal

    Champs OBLIGATOIRES :
        status, analysis_id, analyzed_at, meal_type,
        vision (provider, labels_detected, confidence_threshold_used, labels_count),
        nutrition (ingredients_matched, ingredients_not_found, meal_totals),
        daily_needs (calorie_target, protein_target_g, carbs_target_g, fat_target_g, method),
        meal_balance (calories_pct, protein_pct, carbs_pct, fat_pct, assessment)

    Champs OPTIONNELS :
        recommendation (absent si Ollama indisponible)
    """
    status:         str
    analysis_id:    str                     # MongoDB ObjectId de la trace
    analyzed_at:    str                     # ISO 8601
    meal_type:      Literal["breakfast", "lunch", "dinner", "snack"]
    vision:         VisionSummary
    nutrition:      NutritionSummary
    daily_needs:    DailyNeeds
    meal_balance:   MealBalance
    recommendation: Optional[str] = None   # texte Ollama — absent si service indisponible


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API — GET /users/{user_id}/daily-needs
# ─────────────────────────────────────────────────────────────────────────────

class DailyNeedsDetail(BaseModel):
    """Besoins nutritionnels journaliers calculés via Harris-Benedict révisé."""
    bmr_kcal:         float   # Métabolisme de base (kcal)
    tdee_kcal:        float   # Dépense énergétique totale (kcal)
    calorie_target:   float   # Cible calorique ajustée selon l'objectif
    protein_target_g: float
    carbs_target_g:   float
    fat_target_g:     float
    goal:             str     # ex: "fat_loss" | "muscle_gain" | "maintenance"


class DailyNeedsResponse(BaseModel):
    status:      Literal["success"]
    user_id:     str
    first_name:  Optional[str] = None
    daily_needs: DailyNeedsDetail


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API — GET /ingredients/search
# ─────────────────────────────────────────────────────────────────────────────

class IngredientResult(BaseModel):
    """Un ingrédient retourné par la recherche plein-texte."""
    ingredient_id: str
    name:          str
    category:      Optional[str] = None
    nutriscore:    Optional[str] = None
    calories_g:    float
    protein_g:     float
    carbs_g:       float
    fat_g:         float
    fiber_g:       float


class IngredientSearchResponse(BaseModel):
    status:  Literal["success"]
    query:   str
    count:   int
    results: list[IngredientResult]


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API — GET /users/{user_id}/analyses
# ─────────────────────────────────────────────────────────────────────────────

class MealAnalysisSummary(BaseModel):
    """Vue compacte d'une analyse — utilisée dans le listing historique."""
    analyzed_at:              str
    meal_type:                str
    calories:                 float
    ingredients_matched:      int
    recommendation_available: bool


class UserAnalysesResponse(BaseModel):
    status:   Literal["success"]
    user_id:  str
    count:    int
    analyses: list[MealAnalysisSummary]
