"""
conftest.py — Fixtures partagées entre tous les fichiers de tests.
Ce fichier est chargé automatiquement par pytest avant chaque session.
"""
import os
import sys

# Injection de la clé API factice AVANT tout import du module app
# (pydantic-settings lit les env vars au chargement de config.py)
os.environ.setdefault("HUGGINGFACE_API_KEY", "hf_test_key_factice")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_NAME", "database")
os.environ.setdefault("DB_USER", "admin")
os.environ.setdefault("DB_PASSWORD", "secret")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27018")
os.environ.setdefault("MONGO_DB_NAME", "test_db")

# Ajoute la racine du projet au path Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


# ── Profil utilisateur réutilisable dans les tests ────────────────────────────
@pytest.fixture
def user_male_30():
    """Utilisateur masculin, 30 ans (birth_date=None → défaut 30), 70 kg, 175 cm."""
    return {
        "user_id":          "USR_TEST_01",
        "first_name":       "Test",
        "current_weight_kg": 70.0,
        "height_cm":        175.0,
        "birth_date":       None,
        "gender_code":      1,
        "goal_label":       "General Wellness",
        "diet_type":        "NONE",
        "allergies":        "NONE",
    }


@pytest.fixture
def user_female_30():
    """Utilisatrice féminine, 30 ans, 60 kg, 165 cm."""
    return {
        "user_id":          "USR_TEST_02",
        "first_name":       "TestF",
        "current_weight_kg": 60.0,
        "height_cm":        165.0,
        "birth_date":       None,
        "gender_code":      2,
        "goal_label":       "Weight Loss",
        "diet_type":        "NONE",
        "allergies":        "NONE",
    }


@pytest.fixture
def sample_ingredient():
    """Ingrédient simple avec toutes les colonnes nutritionnelles."""
    return {
        "ingredient_id": "ING_TEST_001",
        "name":          "Chicken",
        "category":      "MEAT",
        "calories_g":    165.0,
        "protein_g":     31.0,
        "carbs_g":       0.0,
        "fat_g":         3.6,
        "fiber_g":       0.0,
        "usda_name":     "Chicken, broilers, breast, raw",
        "nutriscore":    "A",
        "price_per_kg":  9.50,
    }


@pytest.fixture
def labels_pizza():
    """Labels typiques pour une pizza — cas de déduplication sémantique."""
    return [
        {
            "label":       "pizza",
            "description": "Neapolitan pizza with mozzarella cheese, tomato sauce and fresh basil",
            "score":       0.99,
        },
        {
            "label":       "mozzarella cheese",
            "description": "Fresh melted mozzarella cheese on pizza",
            "score":       0.97,
        },
        {
            "label":       "tomato sauce",
            "description": "Red tomato sauce spread across pizza base",
            "score":       0.96,
        },
        {
            "label":       "basil",
            "description": "Fresh basil leaves on top",
            "score":       0.95,
        },
    ]


@pytest.fixture
def labels_balanced_plate():
    """Labels pour une assiette équilibrée — aucun composant, tous conservés."""
    return [
        {"label": "salmon",   "description": "Grilled salmon fillet", "score": 0.98},
        {"label": "rice",     "description": "White rice",             "score": 0.95},
        {"label": "broccoli", "description": "Steamed broccoli",       "score": 0.92},
    ]
