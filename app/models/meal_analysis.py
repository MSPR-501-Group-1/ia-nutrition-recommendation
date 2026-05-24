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
    label:       str            = Field(examples=["poulet rôti"])
    description: Optional[str] = Field(default=None, examples=["Morceaux de poulet grillé dorés"])
    score:       float          = Field(ge=0.0, le=1.0, examples=[0.94])


class VisionResult(BaseModel):
    """Résultat brut du modèle vision — utilisé aussi dans MealAnalysisDocument (MongoDB)."""
    provider:                  str   = Field(examples=["huggingface"])
    labels_detected:           list[DetectedLabel]
    confidence_threshold_used: float = Field(examples=[0.40])


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Nutrition (internes, utilisés pour MongoDB et les calculs)
# ─────────────────────────────────────────────────────────────────────────────

class IngredientMatch(BaseModel):
    """Ingrédient matché dans PostgreSQL — utilisé dans MealAnalysisDocument."""
    ingredient_id:  str             = Field(examples=["ING_0042"])
    name:           str             = Field(examples=["Poulet rôti"])
    calories_g:     float           = Field(examples=[165.0])
    protein_g:      float           = Field(examples=[31.0])
    carbs_g:        float           = Field(examples=[0.0])
    fat_g:          float           = Field(examples=[3.6])
    fiber_g:        Optional[float] = Field(default=None, examples=[0.0])
    detected_label: str             = Field(examples=["roasted chicken"])
    confidence:     float           = Field(examples=[0.94])
    quantity_grams: int             = Field(default=100, examples=[150])


class MealTotals(BaseModel):
    calories:  float = Field(examples=[520.0])
    protein_g: float = Field(examples=[38.5])
    carbs_g:   float = Field(examples=[45.2])
    fat_g:     float = Field(examples=[18.3])
    fiber_g:   float = Field(examples=[6.1])


class NutritionResult(BaseModel):
    ingredients_matched:   list[IngredientMatch]
    ingredients_not_found: list[str] = Field(examples=[["tomates cerises"]])
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
    filename:       Optional[str]       = Field(default=None, examples=["repas_midi.jpg"])
    ai_predictions: list[DetectedLabel]


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API DÉFINITIF — POST /users/{user_id}/analyze-meal
# ─────────────────────────────────────────────────────────────────────────────

class MacroBreakdown(BaseModel):
    """
    Valeurs nutritionnelles pour la quantité réellement servie (pas pour 100g).
    Toutes les valeurs sont en grammes sauf `calories` (kcal).
    """
    calories:  float = Field(examples=[247.5])
    protein_g: float = Field(examples=[46.5])
    carbs_g:   float = Field(examples=[22.0])
    fat_g:     float = Field(examples=[5.4])
    fiber_g:   float = Field(examples=[3.2])


class MatchedIngredientDetail(BaseModel):
    """
    Ingrédient identifié par la vision IA ET matché dans PostgreSQL.
    Les macros sont déjà calculées pour la `quantity_grams` servie.
    """
    ingredient_id:  str   = Field(examples=["ING_0042"])
    name:           str   = Field(examples=["Poulet rôti"])
    detected_label: str   = Field(examples=["roasted chicken"])
    confidence:     float = Field(ge=0.0, le=1.0, examples=[0.94])
    quantity_grams: int   = Field(default=100, ge=1, examples=[150])
    macros:         MacroBreakdown


class VisionSummary(BaseModel):
    """Résumé de l'étape vision — ce que l'IA a vu dans la photo."""
    provider:                  str   = Field(examples=["huggingface"])
    labels_detected:           list[DetectedLabel]
    confidence_threshold_used: float = Field(examples=[0.40])
    labels_count:              int   = Field(examples=[4])


class NutritionSummary(BaseModel):
    """Résultat de l'étape nutrition — ce qui a été matché dans la DB."""
    ingredients_matched:   list[MatchedIngredientDetail]
    ingredients_not_found: list[str]     = Field(examples=[["tomates cerises"]])
    meal_totals:           MacroBreakdown


class DailyNeeds(BaseModel):
    """
    Besoins journaliers estimés via Mifflin-St Jeor.
    `method` indique la formule et les hypothèses utilisées.
    """
    calorie_target:   float = Field(examples=[1900.0])
    protein_target_g: float = Field(examples=[142.5])
    carbs_target_g:   float = Field(examples=[213.8])
    fat_target_g:     float = Field(examples=[52.8])
    method:           str   = Field(examples=["harris_benedict_fat_loss"])


class MealBalance(BaseModel):
    """
    Pourcentage de la cible journalière couvert par ce repas.
    `assessment` : "light" < 15% < "balanced" < 50% < "heavy"
    """
    calories_pct: float                                 = Field(examples=[27.4])
    protein_pct:  float                                 = Field(examples=[33.2])
    carbs_pct:    float                                 = Field(examples=[21.1])
    fat_pct:      float                                 = Field(examples=[19.0])
    assessment:   Literal["light", "balanced", "heavy"] = Field(examples=["balanced"])


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
    status:         str  = Field(examples=["success"])
    analysis_id:    str  = Field(examples=["6650aef3b1e4c2d8a3f7b091"])
    analyzed_at:    str  = Field(examples=["2026-05-23T12:34:56Z"])
    meal_type:      Literal["breakfast", "lunch", "dinner", "snack"] = Field(examples=["lunch"])
    vision:         VisionSummary
    nutrition:      NutritionSummary
    daily_needs:    DailyNeeds
    meal_balance:   MealBalance
    recommendation: Optional[str] = Field(
        default=None,
        examples=["Votre déjeuner est bien équilibré en protéines (33 % des besoins). Pensez à ajouter des légumes verts pour couvrir votre apport en fibres."],
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API — GET /users/{user_id}/daily-needs
# ─────────────────────────────────────────────────────────────────────────────

class DailyNeedsDetail(BaseModel):
    """Besoins nutritionnels journaliers calculés via Harris-Benedict révisé."""
    bmr_kcal:         float = Field(examples=[1583.2])
    tdee_kcal:        float = Field(examples=[1899.8])
    calorie_target:   float = Field(examples=[1399.8])
    protein_target_g: float = Field(examples=[131.2])
    carbs_target_g:   float = Field(examples=[157.5])
    fat_target_g:     float = Field(examples=[38.9])
    goal:             str   = Field(examples=["fat_loss"])


class DailyNeedsResponse(BaseModel):
    status:      Literal["success"]
    user_id:     str             = Field(examples=["usr_abc123"])
    first_name:  Optional[str]  = Field(default=None, examples=["Sophie"])
    daily_needs: DailyNeedsDetail


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API — GET /ingredients/search
# ─────────────────────────────────────────────────────────────────────────────

class IngredientResult(BaseModel):
    """Un ingrédient retourné par la recherche plein-texte."""
    ingredient_id: str             = Field(examples=["ING_0042"])
    name:          str             = Field(examples=["Poulet rôti"])
    category:      Optional[str]  = Field(default=None, examples=["MEAT"])
    nutriscore:    Optional[str]  = Field(default=None, examples=["B"])
    calories_g:    float           = Field(examples=[165.0])
    protein_g:     float           = Field(examples=[31.0])
    carbs_g:       float           = Field(examples=[0.0])
    fat_g:         float           = Field(examples=[3.6])
    fiber_g:       float           = Field(examples=[0.0])


class IngredientSearchResponse(BaseModel):
    status:  Literal["success"]
    query:   str              = Field(examples=["poulet"])
    count:   int              = Field(examples=[3])
    results: list[IngredientResult]


# ─────────────────────────────────────────────────────────────────────────────
# CONTRAT API — GET /users/{user_id}/analyses
# ─────────────────────────────────────────────────────────────────────────────

class MealAnalysisSummary(BaseModel):
    """Vue compacte d'une analyse — utilisée dans le listing historique."""
    analyzed_at:              str   = Field(examples=["2026-05-23T12:34:56Z"])
    meal_type:                str   = Field(examples=["lunch"])
    calories:                 float = Field(examples=[520.0])
    ingredients_matched:      int   = Field(examples=[3])
    recommendation_available: bool  = Field(examples=[True])


class UserAnalysesResponse(BaseModel):
    status:   Literal["success"]
    user_id:  str                      = Field(examples=["usr_abc123"])
    count:    int                      = Field(examples=[5])
    analyses: list[MealAnalysisSummary]
