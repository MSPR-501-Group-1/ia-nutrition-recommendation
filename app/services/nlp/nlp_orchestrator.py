# app/services/nlp/nlp_orchestrator.py
# Orchestre les appels Ollama pour recommandations et plans de repas.

from app.services.nlp.ollama_client import get_ollama_recommendation
from app.config import settings
import httpx


async def generate_meal_recommendation(
    user_profile: dict,
    meal_totals: dict,
    daily_needs: dict,
) -> str:
    """
    Génère un conseil nutritionnel personnalisé via Ollama.
    Contexte : profil utilisateur + bilan macros du repas vs besoins journaliers.
    """
    goal    = user_profile.get("goal_label", "maintien du poids")
    name    = user_profile.get("first_name", "l'utilisateur")
    allergy = user_profile.get("allergies") or "aucune"

    user_data = {
        "goal":      goal,
        "name":      name,
        "allergies": allergy,
    }

    meal_balance = {
        "calories":  f"{meal_totals.get('calories', 0)} kcal "
                     f"(cible : {daily_needs.get('calorie_target', 0)} kcal/j)",
        "proteines": f"{meal_totals.get('protein_g', 0)} g "
                     f"(cible : {daily_needs.get('protein_target_g', 0)} g/j)",
        "glucides":  f"{meal_totals.get('carbs_g', 0)} g "
                     f"(cible : {daily_needs.get('carbs_target_g', 0)} g/j)",
        "lipides":   f"{meal_totals.get('fat_g', 0)} g "
                     f"(cible : {daily_needs.get('fat_target_g', 0)} g/j)",
    }

    try:
        return await get_ollama_recommendation(user_data, meal_balance)
    except Exception:
        cal = meal_totals.get('calories', 0)
        target = daily_needs.get('calorie_target', 0)
        return (
            f"Bilan du repas : {cal} kcal pour un objectif de {target} kcal/j "
            f"({goal}). "
            "Recommandation IA indisponible (Ollama non démarré) — "
            "installez et lancez Ollama avec `ollama serve` puis `ollama pull mistral`."
        )


async def generate_meal_plan(
    user_profile: dict,
    available_ingredients: list[dict],
    days: int = 7,
) -> dict:
    """
    Génère un plan de repas sur N jours via Ollama.
    Retourne un dict {day_1: {...}, day_2: {...}, ...}.
    """
    goal        = user_profile.get("goal_label", "equilibre alimentaire")
    diet_type   = user_profile.get("diet_type", "standard")
    allergies   = user_profile.get("allergies") or "aucune"
    first_name  = user_profile.get("first_name", "")

    ingredient_names = [i["name"] for i in available_ingredients[:30]]
    ingredient_list  = ", ".join(ingredient_names)

    prompt = (
        f"Tu es un diététicien expert. Crée un plan de repas sur {days} jours "
        f"pour {first_name}, dont l'objectif est : {goal}.\n"
        f"Régime alimentaire : {diet_type}. Allergies : {allergies}.\n"
        f"Utilise de préférence ces aliments disponibles : {ingredient_list}.\n\n"
        f"Pour chaque jour, fournis : petit-déjeuner, déjeuner, dîner et collation.\n"
        f"Réponds en JSON structuré avec les clés day_1 à day_{days}, "
        f"chaque jour ayant les clés breakfast, lunch, dinner, snack.\n"
        f"Pour chaque repas, donne : name (nom du repas), ingredients (liste), "
        f"estimated_calories (int)."
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model":  settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=180.0,
            )
            raw = response.json().get("response", "")

        # Tentative de parse JSON — llama3.1 peut envelopper en ```json ... ```
        import json, re
        clean = raw.strip()
        # Retire les balises markdown code block si présentes
        md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean)
        if md_match:
            clean = md_match.group(1).strip()
        # Sinon essaie d'extraire le premier objet JSON dans la réponse
        if not clean.startswith("{"):
            json_match = re.search(r"\{[\s\S]*\}", clean)
            clean = json_match.group(0) if json_match else clean
        try:
            plan = json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            plan = {"raw_plan": raw, "note": "parsing JSON échoué — réponse texte brute"}

        return plan

    except Exception as exc:
        return {
            "error": f"Ollama indisponible : {exc}",
            "note":  "Vérifiez que le service Ollama est lancé sur "
                     f"{settings.ollama_base_url}.",
        }
