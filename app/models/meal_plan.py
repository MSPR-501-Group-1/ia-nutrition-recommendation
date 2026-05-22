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
    calories:   float
    protein_g:  float
    carbs_g:    float
    fat_g:      float
    fiber_g:    float
    sugar_g:    Optional[float] = None   # absent pour certains ingrédients ETL
    sodium_mg:  Optional[float] = None


class RecipeIngredient(BaseModel):
    ingredient_id:       str            # FK → PostgreSQL ingredient.ingredient_id
    name:                str
    category:            Literal[        # ingredient_category_enum
        "VEGETABLE", "FRUIT", "MEAT", "DAIRY",
        "GRAIN", "BEVERAGE", "SNACK", "OTHER"
    ]
    nutriscore:          Optional[Literal["A", "B", "C", "D", "E"]] = None
    quantity_g:          float          # quantité réelle servie (g)
    unit:                Literal["g", "ml", "unit", "tbsp", "tsp"] = "g"
    macros_per_serving:  MacrosPerServing
    estimated_cost_eur:  Optional[float] = None  # calculé côté backend (à implémenter)


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Résumé nutritionnel d'un repas
# ─────────────────────────────────────────────────────────────────────────────

class NutritionalSummary(BaseModel):
    calories:  float
    protein_g: float
    carbs_g:   float
    fat_g:     float
    fiber_g:   float


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Recette
# ─────────────────────────────────────────────────────────────────────────────

class Recipe(BaseModel):
    recipe_id:             str            # FK → PostgreSQL recipe.recipe_id
    title:                 str
    instructions:          str

    # Champs optionnels : absents en DB, fournis par Ollama si disponibles
    prep_time_min:         Optional[int]  = None
    cook_time_min:         Optional[int]  = None
    servings:              Optional[int]  = Field(default=1, ge=1)
    image_url:             Optional[str]  = None
    nutriscore:            Optional[Literal["A", "B", "C", "D", "E"]] = None
    tags:                  Optional[list[str]] = None   # ex: ["gluten-free", "high-protein"]

    ingredients:           list[RecipeIngredient]
    nutritional_summary:   NutritionalSummary
    estimated_cost_eur:    Optional[float] = None
    ai_notes:              Optional[list[str]] = None   # conseils Ollama


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Repas dans un jour
# ─────────────────────────────────────────────────────────────────────────────

class Meal(BaseModel):
    meal_type:      Literal["breakfast", "lunch", "dinner", "snack"]
    time_suggested: Optional[str] = None  # format "HH:MM"
    recipe:         Recipe


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Jour du plan
# ─────────────────────────────────────────────────────────────────────────────

class DailyPlan(BaseModel):
    day_number:           int             # 1 à N
    date:                 Optional[str]   = None   # format ISO "YYYY-MM-DD"
    total_calories:       float
    total_macros:         NutritionalSummary
    estimated_cost_eur:   Optional[float] = None
    meals:                list[Meal]


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Liste de courses
# ─────────────────────────────────────────────────────────────────────────────

class ShoppingItem(BaseModel):
    ingredient_id:       str
    name:                str
    total_quantity_g:    float
    unit:                str = "g"
    estimated_cost_eur:  Optional[float] = None


class ShoppingCategory(BaseModel):
    category: str
    items:    list[ShoppingItem]


class ShoppingList(BaseModel):
    total_estimated_cost_eur: Optional[float] = None
    currency:                 str = "EUR"
    note:                     Optional[str] = None
    grouped_by_category:      list[ShoppingCategory]


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Métadonnées du plan
# ─────────────────────────────────────────────────────────────────────────────

class TargetMacros(BaseModel):
    protein_g: float
    carbs_g:   float
    fat_g:     float


class PlanMetadata(BaseModel):
    duration_days:                int
    target_calories_daily:        float
    target_macros:                TargetMacros
    budget_constraint_eur:        Optional[float] = None
    estimated_weekly_cost_eur:    Optional[float] = None
    diet_type:                    Optional[str]   = None   # diet_type_enum
    excluded_allergens:           Optional[list[str]] = None  # allergies_enum list


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Contexte utilisateur (données anonymisées dans la réponse)
# ─────────────────────────────────────────────────────────────────────────────

class UserContext(BaseModel):
    user_id:    str
    first_name: Optional[str]       = None
    goal:       Optional[str]       = None   # health_goal_enum label
    diet_type:  Optional[str]       = None
    allergies:  Optional[list[str]] = None
    height_cm:  Optional[float]     = None
    weight_kg:  Optional[float]     = None


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-MODÈLES — Insights nutritionnels IA
# ─────────────────────────────────────────────────────────────────────────────

class NutritionalInsights(BaseModel):
    weekly_average_calories: Optional[float]       = None
    weekly_average_macros:   Optional[NutritionalSummary] = None
    balance_score:           Optional[float]       = Field(default=None, ge=0.0, le=1.0)
    detected_deficits:       Optional[list[str]]   = None   # ex: ["fiber", "iron"]
    detected_excesses:       Optional[list[str]]   = None   # ex: ["sodium"]
    ai_global_recommendation: Optional[str]        = None   # texte Ollama


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
    status:           str                      # "success" | "error"
    request_id:       str                      # UUID trace
    generated_at:     str                      # ISO 8601
    ai_model:         Optional[str]  = None    # ex: "mistral:7b"
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # --- Données ---
    user_context:          Optional[UserContext]         = None
    plan_metadata:         PlanMetadata
    daily_plans:           list[DailyPlan]
    shopping_list:         Optional[ShoppingList]        = None
    nutritional_insights:  Optional[NutritionalInsights] = None
