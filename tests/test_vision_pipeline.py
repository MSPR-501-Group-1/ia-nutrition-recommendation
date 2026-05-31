"""
test_vision_pipeline.py — Tests unitaires du pipeline vision
Type : UNITAIRE — fonctions pures, aucun mock nécessaire.

Couvre :
  - _remove_sub_components() : déduplication sémantique des labels HuggingFace
  - _estimate_portion()      : estimation des portions par catégorie/rôle
"""
import pytest
from app.services.vision.analyze_meal_service import (
    _remove_sub_components,
    _estimate_portion,
)


# ─────────────────────────────────────────────
# _remove_sub_components
# ─────────────────────────────────────────────

class TestRemoveSubComponents:
    def test_pizza_supprime_ses_composants(self, labels_pizza):
        """
        Pizza (0.99) décrit mozzarella, tomato sauce et basil dans sa description.
        Seul 'pizza' doit être conservé.
        """
        result = _remove_sub_components(labels_pizza)
        assert len(result) == 1
        assert result[0]["label"] == "pizza"

    def test_assiette_equilibree_tout_conserve(self, labels_balanced_plate):
        """
        Salmon, rice, broccoli sont indépendants.
        Aucun n'apparaît dans la description des autres → tous conservés.
        """
        result = _remove_sub_components(labels_balanced_plate)
        assert len(result) == 3
        labels = [item["label"] for item in result]
        assert "salmon" in labels
        assert "rice"   in labels
        assert "broccoli" in labels

    def test_liste_vide(self):
        assert _remove_sub_components([]) == []

    def test_un_seul_label(self):
        labels = [{"label": "chicken", "description": "grilled chicken breast", "score": 0.95}]
        result = _remove_sub_components(labels)
        assert len(result) == 1
        assert result[0]["label"] == "chicken"

    def test_ordre_par_score_decroissant(self):
        """
        Le label avec le score le plus élevé est traité en premier.
        Ici 'burger' (0.99) garde 'beef patty' (0.90) qui est dans sa description.
        """
        labels = [
            {"label": "beef patty",   "description": "Grilled beef patty",                    "score": 0.90},
            {"label": "burger",       "description": "Burger with beef patty and lettuce",     "score": 0.99},
            {"label": "lettuce",      "description": "Fresh green lettuce leaf",               "score": 0.85},
        ]
        result = _remove_sub_components(labels)
        result_labels = [item["label"] for item in result]
        assert "burger" in result_labels
        assert "beef patty" not in result_labels
        assert "lettuce" not in result_labels

    def test_description_absente_ne_leve_pas_exception(self):
        """Labels sans clé 'description' ne doivent pas lever d'exception."""
        labels = [
            {"label": "chicken", "score": 0.95},
            {"label": "rice",    "score": 0.90},
        ]
        result = _remove_sub_components(labels)
        assert len(result) == 2

    def test_score_ex_aequo_conserve_les_deux(self):
        """Deux labels avec le même score — ni l'un ni l'autre n'est composant de l'autre."""
        labels = [
            {"label": "apple",  "description": "Red apple",  "score": 0.90},
            {"label": "orange", "description": "Navel orange", "score": 0.90},
        ]
        result = _remove_sub_components(labels)
        assert len(result) == 2


# ─────────────────────────────────────────────
# _estimate_portion
# ─────────────────────────────────────────────

class TestEstimatePortion:
    def test_herbe_aromatique_5g(self):
        """basil, parsley, thyme → portion fixe 5g (garnish)."""
        assert _estimate_portion("basil",   "VEGETABLE") == pytest.approx(5.0)
        assert _estimate_portion("parsley", "VEGETABLE") == pytest.approx(5.0)
        assert _estimate_portion("thyme",   "VEGETABLE") == pytest.approx(5.0)

    def test_epice_2g(self):
        """salt, pepper, cumin → portion fixe 2g (spice)."""
        assert _estimate_portion("salt",   "OTHER") == pytest.approx(2.0)
        assert _estimate_portion("pepper", "OTHER") == pytest.approx(2.0)
        assert _estimate_portion("cumin",  "OTHER") == pytest.approx(2.0)

    def test_huile_12g(self):
        """olive oil, butter → portion fixe 12g (oil)."""
        assert _estimate_portion("olive oil", "OTHER") == pytest.approx(12.0)
        assert _estimate_portion("butter",    "DAIRY") == pytest.approx(12.0)

    def test_sauce_30g(self):
        """tomato sauce, ketchup → portion 30g (sauce)."""
        assert _estimate_portion("tomato sauce", "OTHER") == pytest.approx(30.0)
        assert _estimate_portion("ketchup",      "OTHER") == pytest.approx(30.0)

    def test_viande_150g(self):
        """Catégorie MEAT → portion typique 150g."""
        assert _estimate_portion("chicken breast", "MEAT") == pytest.approx(150.0)

    def test_legume_120g(self):
        """Catégorie VEGETABLE → portion typique 120g."""
        assert _estimate_portion("carrot", "VEGETABLE") == pytest.approx(120.0)

    def test_cereale_180g(self):
        """Catégorie GRAIN → portion typique 180g."""
        assert _estimate_portion("rice", "GRAIN") == pytest.approx(180.0)

    def test_categorie_inconnue_100g(self):
        """Catégorie None ou inconnue → 100g par défaut."""
        assert _estimate_portion("unknown food", None)     == pytest.approx(100.0)
        assert _estimate_portion("unknown food", "OTHER")  == pytest.approx(100.0)
