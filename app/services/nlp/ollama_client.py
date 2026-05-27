# app/services/nlp/ollama_client.py
import httpx
from app.config import settings

async def get_ollama_recommendation(user_data, meal_balance):
    """
    Envoie le bilan nutritionnel à Ollama pour obtenir un conseil humain.
    """
    prompt = (
        f"En tant qu'expert en nutrition, analyse ce repas pour un utilisateur "
        f"dont l'objectif est : {user_data['goal']}.\n"
        f"Bilan du repas : {meal_balance}\n"
        f"Allergies : {user_data.get('allergies', 'aucune')}.\n"
        f"Donne un conseil court (3-4 phrases max), motivant et une amélioration précise."
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=180.0,
        )
        return response.json().get("response")