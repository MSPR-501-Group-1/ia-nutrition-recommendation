# app/services/nutrition/calculator_service.py
# Calculs nutritionnels : BMR, TDEE, besoins journaliers, bilan repas.

from datetime import date


# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

# Facteur d'activité : on suppose sédentaire faute de données
_ACTIVITY_FACTOR = 1.2

# Répartition des macros cibles (% des calories)
_PROTEIN_RATIO = 0.30   # 30 % des calories
_CARBS_RATIO   = 0.45   # 45 % des calories
_FAT_RATIO     = 0.25   # 25 % des calories

# Calories par gramme de macronutriment
_KCAL_PER_G_PROTEIN = 4.0
_KCAL_PER_G_CARBS   = 4.0
_KCAL_PER_G_FAT     = 9.0


# ─────────────────────────────────────────────
# FORMULE DE HARRIS-BENEDICT RÉVISÉE
# ─────────────────────────────────────────────

def _calculate_age(birth_date) -> int:
    """Calcule l'âge en années à partir d'une date de naissance."""
    if birth_date is None:
        return 30  # valeur par défaut raisonnable
    today = date.today()
    if hasattr(birth_date, "year"):
        age = today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
    else:
        age = 30
    return max(age, 1)


def calculate_bmr(user: dict) -> float:
    """
    Calcule le métabolisme de base (BMR) avec Harris-Benedict révisé.
    gender_code : 1 = homme, 2 = femme (ou autre → formule femme par défaut).
    """
    weight = float(user.get("current_weight_kg") or 70)
    height = float(user.get("height_cm") or 170)
    age    = _calculate_age(user.get("birth_date"))
    gender = int(user.get("gender_code") or 2)

    if gender == 1:
        bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    else:
        bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

    return round(bmr, 1)


def calculate_daily_needs(user: dict) -> dict:
    """
    Retourne les besoins journaliers complets :
    - TDEE (calories totales)
    - Objectifs en macronutriments (g)
    """
    bmr  = calculate_bmr(user)
    tdee = round(bmr * _ACTIVITY_FACTOR, 1)

    protein_kcal = tdee * _PROTEIN_RATIO
    carbs_kcal   = tdee * _CARBS_RATIO
    fat_kcal     = tdee * _FAT_RATIO

    goal = user.get("goal_label") or "maintenance"

    # Ajustement calorique selon l'objectif
    calorie_target = tdee
    if "loss" in goal.lower() or "perte" in goal.lower():
        calorie_target = round(tdee - 500, 1)   # déficit de 500 kcal
    elif "gain" in goal.lower() or "prise" in goal.lower():
        calorie_target = round(tdee + 300, 1)   # surplus de 300 kcal

    return {
        "bmr_kcal":         bmr,
        "tdee_kcal":        tdee,
        "calorie_target":   calorie_target,
        "protein_target_g": round(protein_kcal / _KCAL_PER_G_PROTEIN, 1),
        "carbs_target_g":   round(carbs_kcal   / _KCAL_PER_G_CARBS,   1),
        "fat_target_g":     round(fat_kcal     / _KCAL_PER_G_FAT,     1),
        "goal":             goal,
    }


# ─────────────────────────────────────────────
# CALCUL DU BILAN D'UN REPAS
# ─────────────────────────────────────────────

def _atwater_calories(protein_g: float, carbs_g: float, fat_g: float) -> float:
    """Formule d'Atwater : protéines×4 + glucides×4 + lipides×9 (kcal/100 g)."""
    return protein_g * 4.0 + carbs_g * 4.0 + fat_g * 9.0


def _reliable_calories(ingredient: dict) -> float:
    """
    Retourne les calories fiables pour 100 g.
    Utilise calories_g de la DB si présente et dans un intervalle plausible
    (10–900 kcal/100 g). Sinon recalcule via Atwater comme dernier recours.
    Note : les données USDA de la seed ont souvent carbs_g=0 sur les produits
    commerciaux, donc Atwater ne sert que de fallback pour les cas vraiment
    absents, pas pour corriger des calories par ailleurs valides.
    """
    cal = float(ingredient.get("calories_g") or 0)
    if 10 <= cal <= 900:
        return cal
    # Fallback Atwater uniquement si calories absentes ou hors plage
    p = float(ingredient.get("protein_g") or 0)
    c = float(ingredient.get("carbs_g")   or 0)
    f = float(ingredient.get("fat_g")     or 0)
    atwater = _atwater_calories(p, c, f)
    return atwater if atwater > 0 else 50.0


def calculate_meal_totals(matched_ingredients: list[dict]) -> dict:
    """
    Additionne les macros de tous les ingrédients détectés.
    Chaque entrée peut contenir quantity_grams (défaut 100 g).
    Les valeurs nutritionnelles dans la DB sont exprimées pour 100 g.
    Les calories sont validées via la formule d'Atwater pour corriger
    automatiquement les données de seed aberrantes.
    """
    totals = {
        "calories":   0.0,
        "protein_g":  0.0,
        "carbs_g":    0.0,
        "fat_g":      0.0,
        "fiber_g":    0.0,
    }

    for ingredient in matched_ingredients:
        ratio = float(ingredient.get("quantity_grams", 100)) / 100.0
        totals["calories"]  += _reliable_calories(ingredient) * ratio
        totals["protein_g"] += float(ingredient.get("protein_g") or 0) * ratio
        totals["carbs_g"]   += float(ingredient.get("carbs_g")   or 0) * ratio
        totals["fat_g"]     += float(ingredient.get("fat_g")     or 0) * ratio
        totals["fiber_g"]   += float(ingredient.get("fiber_g")   or 0) * ratio

    return {k: round(v, 1) for k, v in totals.items()}


def calculate_meal_balance(meal_totals: dict, daily_needs: dict) -> dict:
    """
    Compare les macros du repas aux besoins journaliers.
    Retourne les pourcentages couverts et le statut (ok / under / over).
    """
    def _status(pct: float) -> str:
        if pct < 20:
            return "under"
        if pct > 50:
            return "over"
        return "ok"

    calorie_pct = round(
        meal_totals["calories"] / (daily_needs["calorie_target"] or 1) * 100, 1
    )
    protein_pct = round(
        meal_totals["protein_g"] / (daily_needs["protein_target_g"] or 1) * 100, 1
    )
    carbs_pct = round(
        meal_totals["carbs_g"] / (daily_needs["carbs_target_g"] or 1) * 100, 1
    )
    fat_pct = round(
        meal_totals["fat_g"] / (daily_needs["fat_target_g"] or 1) * 100, 1
    )

    return {
        "calories_pct":  calorie_pct,
        "protein_pct":   protein_pct,
        "carbs_pct":     carbs_pct,
        "fat_pct":       fat_pct,
        "calories_status":  _status(calorie_pct),
        "protein_status":   _status(protein_pct),
        "carbs_status":     _status(carbs_pct),
        "fat_status":       _status(fat_pct),
    }


# ─────────────────────────────────────────────
# PIPELINE D'ANALYSE DE REPAS (utilisé par generate.py)
# ─────────────────────────────────────────────

#: Seuil de confiance appliqué aux labels HuggingFace
CONFIDENCE_THRESHOLD = 0.40


def compute_meal_needs(user: dict) -> dict:
    """
    Estime les besoins journaliers via Mifflin-St Jeor.
    Utilisé dans le pipeline d'analyse de repas photographiés.

    Attend les clés ``weight`` et ``height`` telles que retournées par
    ``queries.get_user_profile`` (contrairement à ``calculate_daily_needs``
    qui attend ``current_weight_kg`` / ``height_cm``).

    Répartition des macros selon l'objectif :
      fat_loss      → 35 % prot / 40 % carbs / 25 % lipides  (−300 kcal)
      muscle_gain   → 30 % prot / 45 % carbs / 25 % lipides  (+200 kcal)
      endurance     → 20 % prot / 55 % carbs / 25 % lipides
      general       → 25 % prot / 50 % carbs / 25 % lipides
    """
    weight = float(user.get("current_weight_kg") or user.get("weight") or 70)
    height = float(user.get("height_cm") or user.get("height") or 170)
    goal   = (user.get("goal_label") or "").lower()

    bmr  = (10 * weight) + (6.25 * height) - (5 * 30) - 161  # Mifflin femme, 30 ans
    tdee = round(bmr * 1.375)

    if "fat_loss" in goal or "perte" in goal:
        calories = max(1200, tdee - 300)
        prot_pct, carb_pct, fat_pct = 0.35, 0.40, 0.25
        method = "mifflin_fat_loss"
    elif "muscle" in goal or "masse" in goal:
        calories = tdee + 200
        prot_pct, carb_pct, fat_pct = 0.30, 0.45, 0.25
        method = "mifflin_muscle_gain"
    elif "endurance" in goal:
        calories = tdee
        prot_pct, carb_pct, fat_pct = 0.20, 0.55, 0.25
        method = "mifflin_endurance"
    else:
        method   = "mifflin_general" if user.get("weight") else "default_2000kcal"
        calories = tdee if user.get("weight") else 2000
        prot_pct, carb_pct, fat_pct = 0.25, 0.50, 0.25

    return {
        "calorie_target":   float(round(calories)),
        "protein_target_g": float(round(calories * prot_pct / 4)),
        "carbs_target_g":   float(round(calories * carb_pct / 4)),
        "fat_target_g":     float(round(calories * fat_pct / 9)),
        "method":           method,
    }


def compute_meal_balance(totals: dict, needs: dict) -> dict:
    """
    Calcule le % de la cible journalière couvert par ce repas.
    Utilisé dans le pipeline d'analyse — retourne ``assessment`` attendu
    par le modèle ``MealBalance``.

      - "light"    : < 15 % des calories journalières
      - "balanced" : 15–50 %
      - "heavy"    : > 50 %
    """
    def _pct(val: float, target: float) -> float:
        return round((val / target) * 100, 1) if target > 0 else 0.0

    cal_pct    = _pct(totals["calories"],  needs["calorie_target"])
    assessment = "light" if cal_pct < 15 else ("heavy" if cal_pct > 50 else "balanced")

    return {
        "calories_pct": cal_pct,
        "protein_pct":  _pct(totals["protein_g"], needs["protein_target_g"]),
        "carbs_pct":    _pct(totals["carbs_g"],   needs["carbs_target_g"]),
        "fat_pct":      _pct(totals["fat_g"],     needs["fat_target_g"]),
        "assessment":   assessment,
    }
