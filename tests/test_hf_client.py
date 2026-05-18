# tests/test_huggingface_client.py

import pytest
import os
import sys
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if "HUGGINGFACE_API_KEY" not in os.environ:
    os.environ["HUGGINGFACE_API_KEY"] = "hf_cle_factice_pour_tests_unitaires"

from app.services.vision.huggingface_client import detect_food_with_hf, MOCK_RESPONSE


def _make_llm_response(content: str):
    """Crée un faux objet de réponse OpenAI chat.completions.create."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.mark.asyncio
async def test_detect_food_succes():
    """Cas nominal : le LLM renvoie un JSON valide d'aliments."""
    fake_image = b"fake_image_bytes"
    fake_json = '[{"label": "frites", "description": "French fries", "score": 0.97}]'
    fake_completion = _make_llm_response(fake_json)

    with patch(
        "app.services.vision.huggingface_client.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_completion)
        mock_client_cls.return_value = mock_client

        resultat = await detect_food_with_hf(fake_image)

    assert resultat == [{"label": "frites", "description": "French fries", "score": 0.97}]
    assert resultat[0]["label"] == "frites"


@pytest.mark.asyncio
async def test_detect_food_succes_avec_markdown():
    """Le LLM enveloppe parfois sa réponse dans ```json ... ``` — doit être géré."""
    fake_image = b"fake_image_bytes"
    fake_json = '```json\n[{"label": "pizza", "description": "Margherita pizza", "score": 0.99}]\n```'
    fake_completion = _make_llm_response(fake_json)

    with patch(
        "app.services.vision.huggingface_client.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_completion)
        mock_client_cls.return_value = mock_client

        resultat = await detect_food_with_hf(fake_image)

    assert resultat[0]["label"] == "pizza"


@pytest.mark.asyncio
async def test_detect_food_fallback_sur_erreur_reseau():
    """Cas d'échec : l'appel LLM lève une exception → retour du mock."""
    with patch(
        "app.services.vision.huggingface_client.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Erreur réseau simulée")
        )
        mock_client_cls.return_value = mock_client

        resultat = await detect_food_with_hf(b"fake_image_bytes")

    assert resultat == MOCK_RESPONSE
    assert resultat[0]["label"] == "chicken"


@pytest.mark.asyncio
async def test_detect_food_fallback_json_invalide():
    """Le LLM renvoie du texte non-JSON → fallback sur le mock."""
    fake_completion = _make_llm_response("Je ne suis pas sûr de ce que je vois.")

    with patch(
        "app.services.vision.huggingface_client.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_completion)
        mock_client_cls.return_value = mock_client

        resultat = await detect_food_with_hf(b"fake_image_bytes")

    assert resultat == MOCK_RESPONSE