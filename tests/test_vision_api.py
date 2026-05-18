import pytest
import os
import sys
import json
from unittest.mock import patch, MagicMock

# Ajout du dossier parent au chemin Python pour trouver le module 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- CORRECTION PYDANTIC ---
# On injecte une fausse clé API si elle n'existe pas déjà pour éviter le crash au moment de l'import
if "HUGGINGFACE_API_KEY" not in os.environ:
    os.environ["HUGGINGFACE_API_KEY"] = "hf_cle_factice_pour_passer_le_test_unitaire"

from app.services.vision.huggingface_client import detect_food_with_hf

@pytest.mark.asyncio
async def test_detect_food_with_hf_success():
    """
    Teste le cas où l'appel à l'API Hugging Face réussit.
    La fonction doit renvoyer la prédiction de l'API.
    """
    fake_image_bytes = b"une_fausse_image_en_octets"
    fake_api_response = [{"label": "broccoli", "score": 0.98}]
    
    # On patch le SDK officiel de Hugging Face
    with patch('app.services.vision.huggingface_client.InferenceClient.object_detection', new_callable=MagicMock) as mock_detect:
        mock_detect.return_value = fake_api_response

        # On appelle la fonction à tester
        resultat = await detect_food_with_hf(fake_image_bytes)

        # On vérifie que le résultat est bien celui de l'API
        assert resultat == fake_api_response
        assert resultat[0]["label"] == "broccoli"
        mock_detect.assert_called_once()

@pytest.mark.asyncio
async def test_detect_food_with_hf_fallback_on_error():
    """
    Teste le cas où l'appel à l'API échoue (ex: erreur 503).
    La fonction doit attraper l'erreur et renvoyer les données de secours (mock).
    """
    fake_image_bytes = b"une_autre_fausse_image"

    # On patch le SDK pour simuler un plantage
    with patch('app.services.vision.huggingface_client.InferenceClient.object_detection', side_effect=Exception("Test SDK error")) as mock_detect:
        resultat = await detect_food_with_hf(fake_image_bytes)

        # On vérifie qu'on a bien reçu les données de secours
        assert len(resultat) == 3
        assert resultat[0]["label"] == "chicken"