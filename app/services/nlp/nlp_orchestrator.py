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
            "Recommandation IA temporairement indisponible."
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

    # Construire les interdictions explicites selon le régime
    forbidden_parts = []
    diet_upper = (diet_type or "").upper()
    if diet_upper in ("VEGETARIAN", "VEGAN"):
        forbidden_parts.append("viande (bœuf, poulet, porc, agneau, veau, dinde, jambon, charcuterie)")
        forbidden_parts.append("poisson et fruits de mer")
    if diet_upper == "VEGAN":
        forbidden_parts.append("produits laitiers (lait, fromage, beurre, crème, yaourt)")
        forbidden_parts.append("œufs")
        forbidden_parts.append("miel")
    allergy_list = allergies if isinstance(allergies, list) else ([allergies] if allergies and allergies != "aucune" else [])
    for allergen in allergy_list:
        forbidden_parts.append(f"tout produit contenant {allergen}")
    forbidden_str = " ; ".join(forbidden_parts) if forbidden_parts else "aucun"

    prompt = (
        f"Tu es un diététicien expert. Crée un plan de repas sur {days} jours "
        f"pour {first_name}, dont l'objectif est : {goal}.\n"
        f"Régime : {diet_type}. Allergies : {allergies}.\n"
        f"INTERDIT (ne jamais utiliser ces aliments) : {forbidden_str}.\n"
        f"Utilise de préférence ces aliments disponibles : {ingredient_list}.\n\n"
        f"Pour chaque jour, fournis : petit-déjeuner, déjeuner, dîner et collation.\n"
        f"Réponds en JSON structuré avec les clés day_1 à day_{days}, "
        f"chaque jour ayant les clés breakfast, lunch, dinner, snack.\n"
        f"Pour chaque repas, donne les champs suivants :\n"
        f"  - name (string) : nom du repas\n"
        f"  - ingredients (array of strings) : liste des ingrédients principaux\n"
        f"  - instructions (string) : étapes de préparation détaillées en 3-5 étapes numérotées\n"
        f"  - estimated_calories (int) : estimation calorique\n"
        f"Réponds uniquement avec le JSON, sans texte avant ni après, sans balises markdown."
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model":  settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_ctx": min(2048 + days * 1024, 8192)},
                },
                timeout=60.0 + days * 30.0,
            )
            if response.status_code != 200:
                body = response.text[:500]
                print(f"[Ollama ERROR] HTTP {response.status_code}: {body}")
                return {"error": f"Ollama HTTP {response.status_code}: {body}"}
            resp_json = response.json()
            if "error" in resp_json:
                print(f"[Ollama ERROR] {resp_json['error']}")
                return {"error": resp_json["error"]}
            raw = resp_json.get("response", "")

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
