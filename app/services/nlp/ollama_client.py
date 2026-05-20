# app/services/nlp/ollama_client.py
import httpx

async def get_ollama_recommendation(user_data, meal_balance):
    """
    Envoie le bilan nutritionnel à Ollama pour obtenir un conseil humain.
    """
    prompt = f"""
    En tant qu'expert en nutrition, analyse ce repas pour un utilisateur dont l'objectif est : {user_data['goal']}.
    Bilan du repas : {meal_balance}
    Contraintes : {user_data.get('allergies')}, Budget : {user_data.get('budget')}.
    Donne un conseil court, motivant et une amélioration précise.
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral", # ou llama3
                "prompt": prompt,
                "stream": False
            },
            timeout=30.0
        )
        return response.json().get("response")