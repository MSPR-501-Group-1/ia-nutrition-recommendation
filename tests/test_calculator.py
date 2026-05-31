"""
test_calculator.py — Tests unitaires de calculator_service.py
Type : UNITAIRE — aucune dépendance externe, aucun mock nécessaire.

Couvre :
  - calculate_bmr()        : Harris-Benedict homme / femme / valeurs par défaut
  - calculate_daily_needs(): objectifs caloriques et macros selon le goal
  - calculate_meal_totals(): somme des macros pondérée par la portion
  - compute_meal_needs()   : Mifflin-St Jeor avec objectifs différents
  - compute_meal_balance() : pourcentages et assessment light/balanced/heavy
"""
import pytest
from app.services.nutrition.calculator_service import (
    calculate_bmr,
    calculate_daily_needs,
    calculate_meal_totals,
    compute_meal_needs,
    compute_meal_balance,
    _normalize_height_cm,
)


# ─────────────────────────────────────────────
# _normalize_height_cm
# ─────────────────────────────────────────────

class TestNormalizeHeight:
    def test_metres_converted_to_cm(self):
        assert _normalize_height_cm(1.75) == pytest.approx(175.0)

    def test_cm_unchanged(self):
        assert _normalize_height_cm(175.0) == pytest.approx(175.0)

    def test_edge_exactly_3(self):
        # 3.0 n'est pas < 3 donc reste tel quel
        assert _normalize_height_cm(3.0) == pytest.approx(3.0)


# ─────────────────────────────────────────────
# calculate_bmr
# ─────────────────────────────────────────────

class TestCalculateBmr:
    def test_homme_30ans_70kg_175cm(self, user_male_30):
        """
        Harris-Benedict homme :
        88.362 + (13.397×70) + (4.799×175) - (5.677×30) = 1695.7
        """
        bmr = calculate_bmr(user_male_30)
        assert bmr == pytest.approx(1695.7, abs=0.5)

    def test_femme_30ans_60kg_165cm(self, user_female_30):
        """
        Harris-Benedict femme :
        447.593 + (9.247×60) + (3.098×165) - (4.330×30) = 1383.7
        """
        bmr = calculate_bmr(user_female_30)
        assert bmr == pytest.approx(1383.7, abs=0.5)

    def test_hauteur_en_metres_normalisee(self):
        """height_cm=1.75 doit être converti en 175 cm avant le calcul."""
        user_m = {"current_weight_kg": 70, "height_cm": 1.75, "birth_date": None, "gender_code": 1}
        user_cm = {"current_weight_kg": 70, "height_cm": 175, "birth_date": None, "gender_code": 1}
        assert calculate_bmr(user_m) == pytest.approx(calculate_bmr(user_cm), abs=0.01)

    def test_valeurs_par_defaut_si_absent(self):
        """Aucun champ fourni → utilise les valeurs par défaut (70kg, 170cm, 30 ans, femme)."""
        bmr = calculate_bmr({})
        assert bmr > 0

    def test_genre_inconnu_utilise_formule_femme(self):
        """gender_code absent → formule femme par défaut."""
        user_sans_genre = {"current_weight_kg": 60, "height_cm": 165, "birth_date": None}
        user_femme      = {"current_weight_kg": 60, "height_cm": 165, "birth_date": None, "gender_code": 2}
        assert calculate_bmr(user_sans_genre) == pytest.approx(calculate_bmr(user_femme), abs=0.01)


# ─────────────────────────────────────────────
# calculate_daily_needs
# ─────────────────────────────────────────────

class TestCalculateDailyNeeds:
    def test_retourne_toutes_les_cles(self, user_male_30):
        needs = calculate_daily_needs(user_male_30)
        for key in ("bmr_kcal", "tdee_kcal", "calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g", "goal"):
            assert key in needs

    def test_objectif_perte_poids_deficit_500kcal(self):
        user = {"current_weight_kg": 70, "height_cm": 175, "birth_date": None,
                "gender_code": 1, "goal_label": "Weight Loss"}
        needs = calculate_daily_needs(user)
        tdee = needs["tdee_kcal"]
        assert needs["calorie_target"] == pytest.approx(tdee - 500, abs=1)

    def test_objectif_prise_masse_surplus_300kcal(self):
        user = {"current_weight_kg": 70, "height_cm": 175, "birth_date": None,
                "gender_code": 1, "goal_label": "Muscle Gain"}
        needs = calculate_daily_needs(user)
        tdee = needs["tdee_kcal"]
        assert needs["calorie_target"] == pytest.approx(tdee + 300, abs=1)

    def test_objectif_maintenance_egal_tdee(self, user_male_30):
        needs = calculate_daily_needs(user_male_30)
        assert needs["calorie_target"] == pytest.approx(needs["tdee_kcal"], abs=1)

    def test_macros_somment_a_100_pourcent(self, user_male_30):
        """30% protéines + 45% glucides + 25% lipides = 100%."""
        needs = calculate_daily_needs(user_male_30)
        cal = needs["calorie_target"]
        protein_cal = needs["protein_target_g"] * 4
        carbs_cal   = needs["carbs_target_g"]   * 4
        fat_cal     = needs["fat_target_g"]      * 9
        assert protein_cal + carbs_cal + fat_cal == pytest.approx(cal, rel=0.05)


# ─────────────────────────────────────────────
# calculate_meal_totals
# ─────────────────────────────────────────────

class TestCalculateMealTotals:
    def test_liste_vide_retourne_zeros(self):
        totals = calculate_meal_totals([])
        assert totals["calories"]  == 0.0
        assert totals["protein_g"] == 0.0
        assert totals["carbs_g"]   == 0.0
        assert totals["fat_g"]     == 0.0
        assert totals["fiber_g"]   == 0.0

    def test_ingredient_simple_100g(self, sample_ingredient):
        sample_ingredient["quantity_grams"] = 100
        totals = calculate_meal_totals([sample_ingredient])
        assert totals["calories"]  == pytest.approx(165.0, abs=1)
        assert totals["protein_g"] == pytest.approx(31.0,  abs=0.1)
        assert totals["fat_g"]     == pytest.approx(3.6,   abs=0.1)

    def test_portion_double_double_les_macros(self, sample_ingredient):
        ing_100 = dict(sample_ingredient, quantity_grams=100)
        ing_200 = dict(sample_ingredient, quantity_grams=200)
        totals_100 = calculate_meal_totals([ing_100])
        totals_200 = calculate_meal_totals([ing_200])
        assert totals_200["calories"]  == pytest.approx(totals_100["calories"]  * 2, abs=1)
        assert totals_200["protein_g"] == pytest.approx(totals_100["protein_g"] * 2, abs=0.1)

    def test_plusieurs_ingredients_additionnes(self, sample_ingredient):
        ing1 = dict(sample_ingredient, quantity_grams=100)
        ing2 = {
            "ingredient_id": "ING_TEST_002", "name": "Broccoli",
            "calories_g": 34.0, "protein_g": 2.8, "carbs_g": 7.0,
            "fat_g": 0.4, "fiber_g": 2.6, "quantity_grams": 120,
        }
        totals = calculate_meal_totals([ing1, ing2])
        # Broccoli: ratio=1.2 → calories=34×1.2=40.8, protein=2.8×1.2=3.36
        assert totals["calories"]  == pytest.approx(165.0 + 40.8, abs=1)
        assert totals["protein_g"] == pytest.approx(31.0 + 3.36,  abs=0.5)

    def test_calories_nulles_utilise_atwater(self):
        """calories_g absent/invalide → Atwater : protein×4 + carbs×4 + fat×9."""
        ing = {
            "ingredient_id": "ING_ATWATER",
            "calories_g":   0.0,     # invalide → fallback Atwater
            "protein_g":    20.0,
            "carbs_g":      30.0,
            "fat_g":        10.0,
            "fiber_g":      0.0,
            "quantity_grams": 100,
        }
        totals = calculate_meal_totals([ing])
        # Atwater = 20×4 + 30×4 + 10×9 = 80+120+90 = 290
        assert totals["calories"] == pytest.approx(290.0, abs=1)

    def test_valeurs_none_traitees_comme_zero(self):
        """Les champs None ne doivent pas lever d'exception."""
        ing = {
            "ingredient_id": "ING_NONE",
            "calories_g":   100.0,
            "protein_g":    None,
            "carbs_g":      None,
            "fat_g":        None,
            "fiber_g":      None,
            "quantity_grams": 100,
        }
        totals = calculate_meal_totals([ing])
        assert totals["protein_g"] == 0.0
        assert totals["fat_g"]     == 0.0


# ─────────────────────────────────────────────
# compute_meal_needs (Mifflin-St Jeor)
# ─────────────────────────────────────────────

class TestComputeMealNeeds:
    def test_fat_loss_retourne_methode_correcte(self):
        user = {"current_weight_kg": 70, "height_cm": 175, "birth_date": None, "goal_label": "fat_loss"}
        needs = compute_meal_needs(user)
        assert needs["method"] == "mifflin_fat_loss"
        assert needs["calorie_target"] >= 1200

    def test_muscle_gain_surplus_calorique(self):
        user = {"current_weight_kg": 70, "height_cm": 175, "birth_date": None, "goal_label": "muscle"}
        needs_base = compute_meal_needs({**user, "goal_label": "general"})
        needs_gain = compute_meal_needs(user)
        assert needs_gain["calorie_target"] > needs_base["calorie_target"]

    def test_endurance_plus_de_glucides(self):
        user = {"current_weight_kg": 70, "height_cm": 175, "birth_date": None, "goal_label": "endurance"}
        needs = compute_meal_needs(user)
        assert needs["method"] == "mifflin_endurance"
        assert needs["carbs_target_g"] > needs["protein_target_g"]

    def test_sans_poids_retourne_2000kcal(self):
        """Profil sans weight → fallback 2000 kcal."""
        needs = compute_meal_needs({})
        assert needs["calorie_target"] == 2000.0
        assert needs["method"] == "default_2000kcal"

    def test_toutes_cles_presentes(self):
        needs = compute_meal_needs({"current_weight_kg": 70, "height_cm": 175, "birth_date": None})
        for key in ("calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g", "method"):
            assert key in needs


# ─────────────────────────────────────────────
# compute_meal_balance
# ─────────────────────────────────────────────

class TestComputeMealBalance:
    @pytest.fixture
    def needs_2000(self):
        return {
            "calorie_target":   2000.0,
            "protein_target_g": 125.0,
            "carbs_target_g":   250.0,
            "fat_target_g":     56.0,
        }

    def test_assessment_light_sous_15_pourcent(self, needs_2000):
        """100 kcal / 2000 = 5% → light."""
        totals = {"calories": 100.0, "protein_g": 5.0, "carbs_g": 10.0, "fat_g": 2.0, "fiber_g": 1.0}
        balance = compute_meal_balance(totals, needs_2000)
        assert balance["assessment"] == "light"
        assert balance["calories_pct"] == pytest.approx(5.0, abs=0.2)

    def test_assessment_balanced_entre_15_et_50(self, needs_2000):
        """500 kcal / 2000 = 25% → balanced."""
        totals = {"calories": 500.0, "protein_g": 30.0, "carbs_g": 50.0, "fat_g": 15.0, "fiber_g": 5.0}
        balance = compute_meal_balance(totals, needs_2000)
        assert balance["assessment"] == "balanced"
        assert balance["calories_pct"] == pytest.approx(25.0, abs=0.2)

    def test_assessment_heavy_plus_50_pourcent(self, needs_2000):
        """1200 kcal / 2000 = 60% → heavy."""
        totals = {"calories": 1200.0, "protein_g": 80.0, "carbs_g": 150.0, "fat_g": 40.0, "fiber_g": 10.0}
        balance = compute_meal_balance(totals, needs_2000)
        assert balance["assessment"] == "heavy"
        assert balance["calories_pct"] == pytest.approx(60.0, abs=0.2)

    def test_target_zero_ne_leve_pas_exception(self):
        """calorie_target=0 ne doit pas produire de ZeroDivisionError."""
        totals = {"calories": 100.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "fiber_g": 0.0}
        needs  = {"calorie_target": 0.0, "protein_target_g": 0.0, "carbs_target_g": 0.0, "fat_target_g": 0.0}
        balance = compute_meal_balance(totals, needs)
        assert "assessment" in balance

    def test_pourcentages_proteines_et_lipides(self, needs_2000):
        totals = {"calories": 500.0, "protein_g": 62.5, "carbs_g": 50.0, "fat_g": 28.0, "fiber_g": 5.0}
        balance = compute_meal_balance(totals, needs_2000)
        assert balance["protein_pct"] == pytest.approx(50.0, abs=0.5)
        assert balance["fat_pct"]     == pytest.approx(50.0, abs=0.5)
