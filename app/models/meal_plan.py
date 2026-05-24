# app/models/meal_plan.py
# Contrat d'API définitif — Plan de repas généré par IA
# Ce fichier sert de documentation vivante ET de validation pour la production.
#
# Route cible : POST /users/{user_id}/meal-plan
# Mock disponible : GET /meal-plan/mock
#
# Légende :
#   - Champ sans Optional  → OBLIGATOIRE (required)
#   - Champ avec Optional  → OPTIONNEL (nullable, peut être absent ou null)

from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Ingrédient dans une recette
# ─────────────────────────────────────────────────────────────────────────────

class MacrosPerServing(BaseModel):
    """Valeurs nutritionnelles pour la quantité servie (pas pour 100g)."""
    calories:   float          = Field(examples=[118.0])
    protein_g:  float          = Field(examples=[20.0])
    carbs_g:    float          = Field(examples=[8.0])
    fat_g:      float          = Field(examples=[0.4])
    fiber_g:    float          = Field(examples=[0.0])
    sugar_g:    Optional[float] = Field(default=None, examples=[6.0])
    sodium_mg:  Optional[float] = Field(default=None, examples=[60.0])


class RecipeIngredient(BaseModel):
    ingredient_id:       str             = Field(examples=["ING_0218"])
    name:                str             = Field(examples=["Yaourt grec nature (0%)"])
    category:            Literal[
        "VEGETABLE", "FRUIT", "MEAT", "DAIRY",
        "GRAIN", "BEVERAGE", "SNACK", "OTHER"
    ]                                    = Field(examples=["DAIRY"])
    nutriscore:          Optional[Literal["A", "B", "C", "D", "E"]] = Field(default=None, examples=["A"])
    quantity_g:          float           = Field(examples=[200.0])
    unit:                Literal["g", "ml", "unit", "tbsp", "tsp"] = Field(default="g", examples=["g"])
    macros_per_serving:  MacrosPerServing
    estimated_cost_eur:  Optional[float] = Field(default=None, examples=[0.55])


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Résumé nutritionnel d'un repas
# ─────────────────────────────────────────────────────────────────────────────

class NutritionalSummary(BaseModel):
    calories:  float = Field(examples=[420.0])
    protein_g: float = Field(examples=[38.0])
    carbs_g:   float = Field(examples=[32.5])
    fat_g:     float = Field(examples=[14.2])
    fiber_g:   float = Field(examples=[4.8])


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Recette
# ─────────────────────────────────────────────────────────────────────────────

class Recipe(BaseModel):
    recipe_id:             str  = Field(examples=["rec_poulet_legumes_001"])
    title:                 str  = Field(examples=["Poulet grillé & légumes vapeur"])
    instructions:          str  = Field(examples=["1. Assaisonner le poulet. 2. Griller 20 min à feu moyen. 3. Cuire les légumes 10 min à la vapeur."])

    # Champs optionnels : absents en DB, fournis par Ollama si disponibles
    prep_time_min:         Optional[int]  = Field(default=None, examples=[10])
    cook_time_min:         Optional[int]  = Field(default=None, examples=[20])
    servings:              Optional[int]  = Field(default=1, ge=1, examples=[1])
    image_url:             Optional[str]  = None
    nutriscore:            Optional[Literal["A", "B", "C", "D", "E"]] = Field(default=None, examples=["A"])
    tags:                  Optional[list[str]] = Field(default=None, examples=[["high-protein", "gluten-free", "low-carb"]])

    ingredients:           list[RecipeIngredient]
    nutritional_summary:   NutritionalSummary
    estimated_cost_eur:    Optional[float] = Field(default=None, examples=[3.20])
    ai_notes:              Optional[list[str]] = Field(default=None, examples=[["Riche en protéines maigres, idéal pour la prise de masse."]])


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Repas dans un jour
# ─────────────────────────────────────────────────────────────────────────────

class Meal(BaseModel):
    meal_type:      Literal["breakfast", "lunch", "dinner", "snack"] = Field(examples=["lunch"])
    time_suggested: Optional[str] = Field(default=None, examples=["12:30"])
    recipe:         Recipe


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Jour du plan
# ─────────────────────────────────────────────────────────────────────────────

class DailyPlan(BaseModel):
    day_number:           int            = Field(examples=[1])
    date:                 Optional[str]  = Field(default=None, examples=["2026-05-23"])
    total_calories:       float          = Field(examples=[1748.0])
    total_macros:         NutritionalSummary
    estimated_cost_eur:   Optional[float] = Field(default=None, examples=[8.20])
    meals:                list[Meal]


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Liste de courses
# ─────────────────────────────────────────────────────────────────────────────

class ShoppingItem(BaseModel):
    ingredient_id:       str             = Field(examples=["ING_0042"])
    name:                str             = Field(examples=["Poulet rôti"])
    total_quantity_g:    float           = Field(examples=[600.0])
    unit:                str             = Field(default="g", examples=["g"])
    estimated_cost_eur:  Optional[float] = Field(default=None, examples=[4.80])


class ShoppingCategory(BaseModel):
    category: str = Field(examples=["VIANDES & POISSONS"])
    items:    list[ShoppingItem]


class ShoppingList(BaseModel):
    total_estimated_cost_eur: Optional[float] = Field(default=None, examples=[57.40])
    currency:                 str             = Field(default="EUR", examples=["EUR"])
    note:                     Optional[str]   = Field(default=None, examples=["Liste pour 7 jours, 1 personne"])
    grouped_by_category:      list[ShoppingCategory]


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Métadonnées du plan
# ─────────────────────────────────────────────────────────────────────────────

class TargetMacros(BaseModel):
    protein_g: float = Field(examples=[140.0])
    carbs_g:   float = Field(examples=[160.0])
    fat_g:     float = Field(examples=[55.0])


class PlanMetadata(BaseModel):
    duration_days:                int              = Field(examples=[7])
    target_calories_daily:        float            = Field(examples=[1750.0])
    target_macros:                TargetMacros
    budget_constraint_eur:        Optional[float]  = Field(default=None, examples=[60.0])
    estimated_weekly_cost_eur:    Optional[float]  = Field(default=None, examples=[57.40])
    diet_type:                    Optional[str]    = Field(default=None, examples=["NONE"])
    excluded_allergens:           Optional[list[str]] = Field(default=None, examples=[["GLUTEN"]])


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Contexte utilisateur (données anonymisées dans la réponse)
# ─────────────────────────────────────────────────────────────────────────────

class UserContext(BaseModel):
    user_id:    str                   = Field(examples=["usr_mock_001"])
    first_name: Optional[str]        = Field(default=None, examples=["Sophie"])
    goal:       Optional[str]        = Field(default=None, examples=["fat_loss"])
    diet_type:  Optional[str]        = Field(default=None, examples=["NONE"])
    allergies:  Optional[list[str]]  = Field(default=None, examples=[["GLUTEN"]])
    height_cm:  Optional[float]      = Field(default=None, examples=[167.0])
    weight_kg:  Optional[float]      = Field(default=None, examples=[68.5])


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Insights nutritionnels IA
# ─────────────────────────────────────────────────────────────────────────────

class NutritionalInsights(BaseModel):
    weekly_average_calories:  Optional[float]             = Field(default=None, examples=[1742.0])
    weekly_average_macros:    Optional[NutritionalSummary] = None
    balance_score:            Optional[float]             = Field(default=None, ge=0.0, le=1.0, examples=[0.87])
    detected_deficits:        Optional[list[str]]         = Field(default=None, examples=[["fiber", "omega_3"]])
    detected_excesses:        Optional[list[str]]         = Field(default=None, examples=[["sodium"]])
    ai_global_recommendation: Optional[str]               = Field(default=None, examples=["Votre plan est globalement équilibré. Augmentez votre apport en fibres en ajoutant des légumineuses 2 fois par semaine."])


# ─────────────────────────────────────────────────────────────────────────────
# MODÈLE RACINE — Réponse complète de POST /users/{user_id}/meal-plan
# ─────────────────────────────────────────────────────────────────────────────

class MealPlanResponse(BaseModel):
    """
    Contrat d'API définitif pour la génération de plans de repas.

    Champs OBLIGATOIRES :
        status, request_id, generated_at, plan_metadata
        (duration_days, target_calories_daily, target_macros),
        daily_plans (day_number, meals, meal_type, recipe.recipe_id,
        recipe.title, recipe.ingredients, macros_per_serving,
        nutritional_summary, estimated_cost_eur)

    Champs OPTIONNELS :
        ai_model, confidence_score, user_context, recipe.prep_time_min,
        recipe.cook_time_min, recipe.servings, recipe.image_url,
        recipe.tags, recipe.ai_notes, shopping_list,
        nutritional_insights, budget_constraint_eur
    """
    # --- Méta-réponse ---
    status:           str             = Field(examples=["success"])
    request_id:       str             = Field(examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"])
    generated_at:     str             = Field(examples=["2026-05-23T08:00:00Z"])
    ai_model:         Optional[str]  = Field(default=None, examples=["mistral:7b"])
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, examples=[0.89])

    # --- Données ---
    user_context:          Optional[UserContext]         = None
    plan_metadata:         PlanMetadata
    daily_plans:           list[DailyPlan]
    shopping_list:         Optional[ShoppingList]        = None
    nutritional_insights:  Optional[NutritionalInsights] = None
