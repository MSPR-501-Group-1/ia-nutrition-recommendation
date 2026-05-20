import pytest
import os
import sys
import json
from unittest.mock import patch, AsyncMock, MagicMock

# Ajout du dossier parent au chemin Python pour trouver le module 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# On injecte une fausse clé API pour éviter le crash à l'import si .env absent
if "HUGGINGFACE_API_KEY" not in os.environ:
    os.environ["HUGGINGFACE_API_KEY"] = "hf_cle_factice_pour_passer_le_test_unitaire"

from app.services.vision.huggingface_client import detect_food_with_hf, MOCK_RESPONSE


def _make_fake_completion(content: str):
    """Construit un objet ChatCompletion minimal pour le mock."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.mark.asyncio
async def test_detect_food_with_hf_success():
    """
    Teste le cas où l'appel à AsyncOpenAI réussit.
    La fonction doit parser la réponse JSON et la retourner.
    """
    fake_image_bytes = b"une_fausse_image_en_octets"
    fake_json = '[{"label": "broccoli", "description": "Fresh broccoli", "score": 0.98}]'
    fake_completion = _make_fake_completion(fake_json)

    mock_create = AsyncMock(return_value=fake_completion)

    with patch("app.services.vision.huggingface_client.AsyncOpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        mock_openai_cls.return_value = mock_client

        resultat = await detect_food_with_hf(fake_image_bytes)

    assert isinstance(resultat, list)
    assert len(resultat) == 1
    assert resultat[0]["label"] == "broccoli"
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_detect_food_with_hf_fallback_on_error():
    """
    Teste le cas où l'appel à l'API échoue.
    La fonction doit attraper l'erreur et retourner MOCK_RESPONSE.
    """
    fake_image_bytes = b"une_autre_fausse_image"

    with patch("app.services.vision.huggingface_client.AsyncOpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        mock_openai_cls.return_value = mock_client

        resultat = await detect_food_with_hf(fake_image_bytes)

    assert resultat == MOCK_RESPONSE
    assert len(resultat) == 3
    assert resultat[0]["label"] == "chicken"