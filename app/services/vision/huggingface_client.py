import asyncio
import base64
import json as json_module

from openai import AsyncOpenAI

# ============================================================
#  CONFIGURATION
# ============================================================
# Modèle vision multimodal Kimi-K2.5 via le provider Novita (router HuggingFace)
_MODEL_ID   = "moonshotai/Kimi-K2.5:novita"
_BASE_URL   = "https://router.huggingface.co/v1"

# Prompt système : demande au LLM une liste JSON d'aliments
_SYSTEM_PROMPT = (
    "You are a food recognition expert. "
    "Analyze the image and identify ALL visible food items. "
    "Return ONLY a valid JSON array — no markdown fences, no explanation. "
    'Format: [{"label": "food name", "description": "brief description", "score": 0.95}]. '
    "Use a score between 0 and 1 to reflect your confidence. "
    "If no food is visible, return an empty array: []"
)

# ============================================================
#  DONNÉES DE SECOURS (MODE MOCK)
# ============================================================
MOCK_RESPONSE = [
    {"label": "chicken",  "description": "Grilled chicken pieces",  "score": 0.98},
    {"label": "broccoli", "description": "Fresh broccoli florets",  "score": 0.95},
    {"label": "rice",     "description": "White cooked rice",       "score": 0.91},
]

# ============================================================
#  COUCHE ASYNC — point d'entrée pour FastAPI
# ============================================================
async def detect_food_with_hf(image_bytes: bytes) -> list:
    """
    Identifie les aliments dans une image via Kimi-K2.5 (LLM vision multimodal).

    Utilise AsyncOpenAI pointé sur router.huggingface.co/v1 pour envoyer
    l'image en base64 et récupérer une liste JSON d'aliments reconnus.
    Retour : liste de dicts {"label", "description", "score"}.
    En cas d'erreur, retourne MOCK_RESPONSE en mode dégradé.
    """
    try:
        from app.config import settings
    except ImportError:
        from app.core.config import settings

    api_key = settings.huggingface_api_key
    print(f"--- DEBUG --- Clé HF (début) : {api_key[:8]}... | Modèle : {_MODEL_ID}")

    # Encode l'image en data URL base64 (format attendu par l'API vision)
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:image/jpeg;base64,{b64}"

    client = AsyncOpenAI(base_url=_BASE_URL, api_key=api_key)

    try:
        completion = await client.chat.completions.create(
            model=_MODEL_ID,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Identify all food items in this image."},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
        )

        raw_text = completion.choices[0].message.content.strip()
        print(f"✅ Réponse brute du modèle : {raw_text[:200]}")

        # Retire d'éventuels blocs markdown ```json ... ``` si le modèle en produit
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        result = json_module.loads(raw_text)
        if not isinstance(result, list):
            raise ValueError(f"Réponse inattendue (pas une liste) : {result}")

        print(f"✅ {len(result)} aliment(s) identifié(s)")
        return result

    except Exception as e:
        print(f"❌ ERREUR KIMI-K2.5 : {e}")
        print("⚠️  PASSAGE EN MODE SECOURS (MOCK)")
        return MOCK_RESPONSE