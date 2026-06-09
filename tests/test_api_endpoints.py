"""
test_api_endpoints.py — Tests d'intégration des endpoints FastAPI
Type : INTÉGRATION — utilise httpx.AsyncClient avec l'app ASGI.
       Toutes les dépendances externes (PostgreSQL, MongoDB, HuggingFace, Ollama)
       sont mockées pour tester uniquement la couche HTTP et la logique de routage.

Couvre :
  - POST /users/{user_id}/analyze-meal : 400, 404, 200
  - POST /users/{user_id}/meal-plan    : 404, 503, 200
"""
import io
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport


# Import de l'app FastAPI
from main import app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_user(user_id: str = "USR_001") -> dict:
    return {
        "user_id":          user_id,
        "first_name":       "Alice",
        "current_weight_kg": 70.0,
        "height_cm":        175.0,
        "birth_date":       None,
        "gender_code":      1,
        "goal_label":       "General Wellness",
        "diet_type":        "NONE",
        "allergies":        "NONE",
    }


def _mock_ingredient() -> dict:
    return {
        "ingredient_id": "ING_TEST_001",
        "name":          "Carrots, raw",
        "category":      "VEGETABLE",
        "calories_g":    41.0,
        "protein_g":     0.93,
        "carbs_g":       9.58,
        "fat_g":         0.24,
        "fiber_g":       2.8,
        "usda_name":     "Carrots, raw",
        "nutriscore":    "A",
        "price_per_kg":  2.50,
    }


# ── Fixture : client HTTP ─────────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ─────────────────────────────────────────────
# POST /users/{user_id}/analyze-meal
# ─────────────────────────────────────────────

class TestAnalyzeMealEndpoint:
    async def test_400_sans_image(self, client):
        """Requête sans fichier → 400 Bad Request."""
        resp = await client.post("/api/v1/users/USR_001/analyze-meal")
        assert resp.status_code == 400

    async def test_400_fichier_non_image(self, client):
        """Fichier texte soumis comme image → 400."""
        resp = await client.post(
            "/api/v1/users/USR_001/analyze-meal",
            files={"file": ("doc.txt", io.BytesIO(b"not an image"), "text/plain")},
            data={"meal_type": "lunch"},
        )
        assert resp.status_code == 400

    async def test_404_utilisateur_inexistant(self, client):
        """Utilisateur absent de PostgreSQL → 404."""
        with patch("app.db.queries.get_user_profile", new_callable=AsyncMock) as mock_user:
            mock_user.return_value = None
            resp = await client.post(
                "/api/v1/users/USR_INEXISTANT/analyze-meal",
                files={"file": ("photo.jpg", io.BytesIO(b"FAKE"), "image/jpeg")},
                data={"meal_type": "lunch"},
            )
        assert resp.status_code == 404

    async def test_200_pipeline_complet_mocke(self, client):
        """
        Cas nominal : tous les services externes sont mockés.
        La réponse doit contenir les clés attendues par le front-end.
        """
        with (
            patch("app.db.queries.get_user_profile",      new_callable=AsyncMock) as mock_user,
            patch("app.services.vision.analyze_meal_service.detect_food_with_hf",
                  new_callable=AsyncMock) as mock_hf,
            patch("app.db.queries.get_ingredient_by_name", new_callable=AsyncMock) as mock_ing,
            patch("app.db.mongo.save_meal_analysis",        new_callable=AsyncMock) as mock_mongo,
            patch("app.db.queries.save_meal_to_postgres",  new_callable=AsyncMock) as mock_pg,
            patch("app.services.nlp.nlp_orchestrator.generate_meal_recommendation",
                  new_callable=AsyncMock) as mock_reco,
        ):
            mock_user.return_value  = _mock_user()
            mock_hf.return_value    = [{"label": "carrot", "description": "sliced carrots", "score": 0.98}]
            mock_ing.return_value   = _mock_ingredient()
            mock_mongo.return_value = "mongo_id_fake_123"
            mock_pg.return_value    = None
            mock_reco.return_value  = "Mangez plus de protéines."

            resp = await client.post(
                "/api/v1/users/USR_001/analyze-meal",
                files={"file": ("photo.jpg", io.BytesIO(b"FAKE_IMAGE"), "image/jpeg")},
                data={"meal_type": "lunch"},
            )

        assert resp.status_code == 200
        data = resp.json()

        # Structure attendue par le front-end (contrat API stable)
        assert data["status"] == "success"
        assert "analysis_id" in data
        assert "meal_type"   in data
        assert "vision"      in data
        assert "nutrition"   in data
        assert "daily_needs" in data
        assert "meal_balance" in data

        # Le label 'carrot' doit être dans les labels détectés
        labels = [l["label"] for l in data["vision"]["labels_detected"]]
        assert "carrot" in labels

        # Les totaux nutritionnels doivent exister
        totals = data["nutrition"]["meal_totals"]
        assert "calories"  in totals
        assert "protein_g" in totals

    async def test_502_huggingface_indisponible(self, client):
        """HuggingFace inaccessible → 502."""
        with (
            patch("app.db.queries.get_user_profile", new_callable=AsyncMock) as mock_user,
            patch("app.services.vision.analyze_meal_service.detect_food_with_hf",
                  new_callable=AsyncMock) as mock_hf,
        ):
            mock_user.return_value = _mock_user()
            mock_hf.side_effect    = Exception("Service HuggingFace timeout")

            resp = await client.post(
                "/api/v1/users/USR_001/analyze-meal",
                files={"file": ("photo.jpg", io.BytesIO(b"FAKE"), "image/jpeg")},
                data={"meal_type": "lunch"},
            )
        assert resp.status_code == 502


# ─────────────────────────────────────────────
# POST /users/{user_id}/meal-plan
# ─────────────────────────────────────────────

class TestMealPlanEndpoint:
    async def test_404_utilisateur_inexistant(self, client):
        with patch("app.db.queries.get_user_profile", new_callable=AsyncMock) as mock_user:
            mock_user.return_value = None
            resp = await client.post("/api/v1/users/USR_INEXISTANT/meal-plan?days=1")
        assert resp.status_code == 404

    async def test_503_ollama_indisponible(self, client):
        """Ollama retourne une erreur → 503."""
        with (
            patch("app.db.queries.get_user_profile",             new_callable=AsyncMock) as mock_user,
            patch("app.db.queries.get_ingredients_for_meal_plan", new_callable=AsyncMock) as mock_ings,
            patch("app.db.queries.get_user_budget",              new_callable=AsyncMock) as mock_budget,
            patch("app.api.routers.nutrition.nlp_generate_meal_plan",
                  new_callable=AsyncMock) as mock_plan,
        ):
            mock_user.return_value   = _mock_user()
            mock_ings.return_value   = []
            mock_budget.return_value = None
            mock_plan.return_value   = {"error": "Ollama unreachable"}

            resp = await client.post("/api/v1/users/USR_001/meal-plan?days=1")
        assert resp.status_code == 503

    async def test_200_plan_1_jour_mocke(self, client):
        """Plan repas sur 1 jour avec mocks → 200 et structure correcte."""
        raw_plan_ollama = {
            "day_1": {
                "breakfast": {
                    "name": "Porridge",
                    "instructions": "Faire chauffer.",
                    "ingredients": [{"name": "Oats", "quantity_g": 80}],
                    "estimated_calories": 310,
                },
            }
        }

        with (
            patch("app.db.queries.get_user_profile",             new_callable=AsyncMock) as mock_user,
            patch("app.db.queries.get_ingredients_for_meal_plan", new_callable=AsyncMock) as mock_ings,
            patch("app.db.queries.get_user_budget",              new_callable=AsyncMock) as mock_budget,
            patch("app.api.routers.nutrition.nlp_generate_meal_plan",
                  new_callable=AsyncMock) as mock_plan,
            patch("app.db.queries.get_ingredient_by_name",       new_callable=AsyncMock) as mock_ing,
        ):
            mock_user.return_value   = _mock_user()
            mock_ings.return_value   = [_mock_ingredient()]
            mock_budget.return_value = 5.0
            mock_plan.return_value   = raw_plan_ollama
            mock_ing.return_value    = _mock_ingredient()

            resp = await client.post("/api/v1/users/USR_001/meal-plan?days=1")

        assert resp.status_code == 200
        data = resp.json()

        assert data["status"]     == "success"
        assert "request_id"       in data
        assert "daily_plans"      in data
        assert "plan_metadata"    in data
        assert "user_context"     in data
        assert len(data["daily_plans"]) == 1
