# app/services/nutrition/meal_plan_adapter.py
# Adaptateur : convertit la sortie brute d'Ollama vers le contrat MealPlanResponse.
#
# Ollama retourne :
#   { "day_1": { "breakfast": { "name": "...", "ingredients": [...], "estimated_calories": 380 }, ... } }
#
# On normalise vers le contrat défini dans app/models/meal_plan.py.
# Les champs impossibles à calculer sans la DB (macros détaillées, coûts)
# sont laissés à None — ils seront enrichis lors de l'intégration DB complète.

from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# Constantes internes
# ─────────────────────────────────────────────────────────────────────────────

EMPTY_MACROS = {
    "calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0,
    "fat_g": 0.0, "fiber_g": 0.0,
}

MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"]


# ─────────────────────────────────────────────────────────────────────────────
# Adaptateur principal
# ─────────────────────────────────────────────────────────────────────────────

def map_ollama_to_contract(
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

        for meal_type in MEAL_ORDER:
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
                    "macros_per_serving": EMPTY_MACROS.copy(),
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
                    **EMPTY_MACROS.copy(),
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
            "total_macros": {**EMPTY_MACROS.copy(), "calories": day_total_cal},
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
