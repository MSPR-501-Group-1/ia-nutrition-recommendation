# app/services/nutrition/meal_plan_adapter.py
# Adaptateur : convertit la sortie brute d'Ollama vers le contrat MealPlanResponse.
# Enrichit les ingrédients via PostgreSQL (macros + prix depuis price_per_kg).

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.queries import get_ingredient_by_name, get_french_ingredient_by_category
from app.services.nutrition.calculator_service import (
    calculate_daily_needs,
    _reliable_calories,
)
from app.services.nutrition.pricing_service import (
    compute_ingredient_cost,
    guess_category_from_name,
    get_price_per_kg,
)

DEFAULT_BUDGET_PER_MEAL = 5.0  # € par repas si aucune préférence en DB

# ─────────────────────────────────────────────────────────────────────────────
# Constantes internes
# ─────────────────────────────────────────────────────────────────────────────

EMPTY_MACROS = {
    "calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0,
    "fat_g": 0.0, "fiber_g": 0.0,
}

MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"]


def _sum_macros(a: dict, b: dict) -> dict:
    return {k: round(a.get(k, 0.0) + b.get(k, 0.0), 2) for k in EMPTY_MACROS}


def _avg_macros(totals: dict, n: int) -> dict:
    if n == 0:
        return EMPTY_MACROS.copy()
    return {k: round(v / n, 1) for k, v in totals.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Adaptateur principal
# ─────────────────────────────────────────────────────────────────────────────

async def map_ollama_to_contract(
    user: dict,
    raw_plan: dict,
    days: int,
    request_id: str,
    db: AsyncSession,
    budget_max_per_meal: float | None = None,
) -> dict:
    """
    Mappe la réponse brute d'Ollama vers le contrat MealPlanResponse.

    Enrichissements effectués :
    - target_calories_daily / target_macros : calculés via Harris-Benedict
    - macros_per_serving : récupérées depuis PostgreSQL via matching par nom
    - estimated_cost_eur : calculé depuis price_per_kg × quantity_g / 1000
    - shopping_list : agrégation de tous les ingrédients du plan
    - nutritional_insights : moyennes hebdomadaires et balance_score
    - ai_model : peuplé depuis settings.ollama_model
    """
    daily_needs = calculate_daily_needs(user)

    allergies = user.get("allergies")
    excluded = [allergies] if allergies and allergies != "NONE" else []

    daily_plans = []
    # Agrégation pour shopping_list : {ingredient_id: {...}}
    shopping_agg: dict[str, dict] = {}

    for i in range(1, days + 1):
        day_raw = raw_plan.get(f"day_{i}", {})
        meals = []
        day_macros = EMPTY_MACROS.copy()
        day_cost = 0.0

        for meal_type in MEAL_ORDER:
            meal_raw = day_raw.get(meal_type)
            if not meal_raw:
                continue

            raw_ings = meal_raw.get("ingredients", [])
            ingredients = []
            recipe_macros = EMPTY_MACROS.copy()
            recipe_cost = 0.0

            for j, ing in enumerate(raw_ings):
                ing_name = ing if isinstance(ing, str) else ing.get("name", str(ing))
                quantity_g = float(
                    ing.get("quantity_g", ing.get("quantity", 100))
                    if isinstance(ing, dict) else 100
                )

                db_ing = await get_ingredient_by_name(db, ing_name)

                # Si le nom retourné est anglais (pas d'accent français), chercher l'équivalent français
                _FRENCH_CHARS = frozenset("éèêëàâùûüôîïœçÉÈÊËÀÂÙÛÜÔÎÏŒÇ")
                if db_ing and not any(c in _FRENCH_CHARS for c in db_ing["name"]):
                    target_cal = float(db_ing.get("calories_g") or 0)
                    french = await get_french_ingredient_by_category(db, db_ing.get("category") or "OTHER", target_cal)
                    if french:
                        db_ing = french

                if db_ing:
                    ratio    = quantity_g / 100.0
                    category = db_ing.get("category") or "OTHER"
                    macros = {
                        "calories":  round(_reliable_calories(db_ing) * ratio, 2),
                        "protein_g": round(float(db_ing.get("protein_g") or 0) * ratio, 2),
                        "carbs_g":   round(float(db_ing.get("carbs_g")   or 0) * ratio, 2),
                        "fat_g":     round(float(db_ing.get("fat_g")     or 0) * ratio, 2),
                        "fiber_g":   round(float(db_ing.get("fiber_g")   or 0) * ratio, 2),
                    }
                    cost = compute_ingredient_cost(
                        category, quantity_g, db_ing.get("price_per_kg")
                    )

                    ing_entry = {
                        "ingredient_id":      db_ing["ingredient_id"],
                        "name":               db_ing["name"],
                        "category":           category,
                        "nutriscore":         db_ing.get("nutriscore"),
                        "quantity_g":         quantity_g,
                        "unit":               "g",
                        "macros_per_serving": macros,
                        "estimated_cost_eur": round(cost, 3),
                    }

                    # Agrégation shopping list
                    key = db_ing["ingredient_id"]
                    if key not in shopping_agg:
                        shopping_agg[key] = {
                            "ingredient_id":   db_ing["ingredient_id"],
                            "name":            db_ing["name"],
                            "category":        category,
                            "total_quantity_g": 0.0,
                            "db_price":        db_ing.get("price_per_kg"),
                        }
                    shopping_agg[key]["total_quantity_g"] += quantity_g

                else:
                    # Ingrédient non trouvé en DB — on devine la catégorie pour le prix
                    category = guess_category_from_name(ing_name)
                    macros   = EMPTY_MACROS.copy()
                    cost     = compute_ingredient_cost(category, quantity_g)

                    ing_entry = {
                        "ingredient_id":      f"ollama_{i}_{meal_type}_{j}",
                        "name":               ing_name,
                        "category":           category,
                        "quantity_g":         quantity_g,
                        "unit":               "g",
                        "macros_per_serving": macros,
                        "estimated_cost_eur": round(cost, 3),
                    }

                    # Agrégation shopping list pour les ingrédients hors DB aussi
                    key = ing_entry["ingredient_id"]
                    if key not in shopping_agg:
                        shopping_agg[key] = {
                            "ingredient_id":   key,
                            "name":            ing_name,
                            "category":        category,
                            "total_quantity_g": 0.0,
                            "db_price":        None,
                        }
                    shopping_agg[key]["total_quantity_g"] += quantity_g

                ingredients.append(ing_entry)
                recipe_macros = _sum_macros(recipe_macros, macros)
                recipe_cost += cost

            # Fallback calories : utiliser l'estimation Ollama si DB n'a rien calculé
            estimated_cal = float(meal_raw.get("estimated_calories", 0))
            if recipe_macros["calories"] == 0 and estimated_cal > 0:
                recipe_macros["calories"] = estimated_cal

            recipe = {
                "recipe_id":    f"ollama_day{i}_{meal_type}",
                "title":        meal_raw.get("name", meal_type.capitalize()),
                "instructions": meal_raw.get(
                    "instructions", "Instructions non fournies par le modèle IA."
                ),
                "ingredients":          ingredients,
                "nutritional_summary":  recipe_macros,
                "prep_time_min":        meal_raw.get("prep_time_min"),
                "cook_time_min":        meal_raw.get("cook_time_min"),
                "servings":             meal_raw.get("servings", 1),
                "tags":                 meal_raw.get("tags"),
                "ai_notes":             meal_raw.get("ai_notes"),
                "estimated_cost_eur":   round(recipe_cost, 2) if recipe_cost > 0 else None,
            }

            meals.append({"meal_type": meal_type, "recipe": recipe})
            day_macros = _sum_macros(day_macros, recipe_macros)
            day_cost += recipe_cost

        daily_plans.append({
            "day_number":       i,
            "total_calories":   day_macros["calories"],
            "total_macros":     day_macros,
            "estimated_cost_eur": round(day_cost, 2) if day_cost > 0 else None,
            "meals":            meals,
        })

    # ── Shopping list ─────────────────────────────────────────────────────────
    category_map: dict[str, list] = defaultdict(list)
    total_shopping_cost = 0.0
    for item in shopping_agg.values():
        cost_item = compute_ingredient_cost(
            item["category"], item["total_quantity_g"], item.get("db_price")
        )
        total_shopping_cost += cost_item
        category_map[item["category"]].append({
            "ingredient_id":      item["ingredient_id"],
            "name":               item["name"],
            "total_quantity_g":   round(item["total_quantity_g"], 0),
            "unit":               "g",
            "estimated_cost_eur": round(cost_item, 2),
        })

    shopping_list = {
        "total_estimated_cost_eur": round(total_shopping_cost, 2) if total_shopping_cost > 0 else None,
        "currency": "EUR",
        "note": f"Liste pour {days} jour{'s' if days > 1 else ''}, 1 personne",
        "grouped_by_category": [
            {"category": cat, "items": items}
            for cat, items in sorted(category_map.items())
        ],
    } if shopping_agg else None

    # ── Nutritional insights ──────────────────────────────────────────────────
    n = len(daily_plans)
    avg_cal = round(sum(d["total_calories"] for d in daily_plans) / n, 1) if n else 0.0
    macro_sum = EMPTY_MACROS.copy()
    for d in daily_plans:
        macro_sum = _sum_macros(macro_sum, d["total_macros"])
    avg_macros   = _avg_macros(macro_sum, n)
    target_cal   = daily_needs["calorie_target"]
    target_prot  = daily_needs["protein_target_g"]
    target_carbs = daily_needs["carbs_target_g"]
    target_fat   = daily_needs["fat_target_g"]
    balance_score = round(min(avg_cal / target_cal, 1.0), 2) if target_cal > 0 else None

    # Déficits et excès — seuil +-10 % de la cible journalière
    _LABELS = {"calories": "calories", "protein": "protéines", "carbs": "glucides", "fat": "lipides"}

    def _ratio(actual, target):
        return actual / target if target else 1.0

    ratios = {
        "calories": _ratio(avg_cal,                         target_cal),
        "protein":  _ratio(avg_macros.get("protein_g", 0), target_prot),
        "carbs":    _ratio(avg_macros.get("carbs_g",   0), target_carbs),
        "fat":      _ratio(avg_macros.get("fat_g",     0), target_fat),
    }

    detected_deficits = [_LABELS[k] for k, r in ratios.items() if r < 0.90] or None
    detected_excesses = [_LABELS[k] for k, r in ratios.items() if r > 1.10] or None

    reco_parts = []
    if detected_deficits:
        reco_parts.append(f"Déficits détectés : {', '.join(detected_deficits)}.")
    if detected_excesses:
        reco_parts.append(f"Excès détectés : {', '.join(detected_excesses)}.")
    if not reco_parts:
        reco_parts.append("Votre plan est bien équilibré sur l'ensemble de la période.")

    nutritional_insights = {
        "weekly_average_calories":  avg_cal,
        "weekly_average_macros":    avg_macros,
        "balance_score":            balance_score,
        "detected_deficits":        detected_deficits,
        "detected_excesses":        detected_excesses,
        "ai_global_recommendation": " ".join(reco_parts),
    }

    return {
        "status":       "success",
        "request_id":   request_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_model":     settings.ollama_model,
        "user_context": {
            "user_id":    user["user_id"],
            "first_name": user.get("first_name"),
            "goal":       user.get("goal_label"),
            "diet_type":  user.get("diet_type"),
            "allergies":  excluded,
            "height_cm":  user.get("height_cm"),
            "weight_kg":  user.get("current_weight_kg"),
        },
        "plan_metadata": {
            "duration_days":           days,
            "target_calories_daily":   daily_needs["calorie_target"],
            "target_macros": {
                "protein_g": daily_needs["protein_target_g"],
                "carbs_g":   daily_needs["carbs_target_g"],
                "fat_g":     daily_needs["fat_target_g"],
            },
            "budget_constraint_eur":     round(
                (budget_max_per_meal or DEFAULT_BUDGET_PER_MEAL) * days * 3, 2
            ),
            "estimated_weekly_cost_eur": round(total_shopping_cost, 2) if total_shopping_cost > 0 else None,
            "diet_type":          user.get("diet_type"),
            "excluded_allergens": excluded,
        },
        "daily_plans":          daily_plans,
        "shopping_list":        shopping_list,
        "nutritional_insights": nutritional_insights,
    }
