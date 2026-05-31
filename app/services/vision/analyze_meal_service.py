# app/services/vision/analyze_meal_service.py
# Pipeline complet d'analyse de repas par photo.
#
# Étapes :
#   1. Profil utilisateur (PostgreSQL)
#   2. Détection des aliments via HuggingFace
#   3. Filtering par seuil de confiance (≥ CONFIDENCE_THRESHOLD)
#   3b. Déduplication sémantique : suppression des composants de plats composites
#   4. Matching dans PostgreSQL → macros
#   5. Calculs nutritionnels (Mifflin-St Jeor)
#   6. Recommandation Ollama (non bloquant)
#   7. Persistance MongoDB + trace PostgreSQL
#   8. Construction de la réponse

from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import mongo, queries
from app.services.nlp.nlp_orchestrator import generate_meal_recommendation
from app.services.nutrition.calculator_service import (
    CONFIDENCE_THRESHOLD,
    _reliable_calories,
    calculate_meal_totals,
    compute_meal_needs,
    compute_meal_balance,
)
from app.services.vision.huggingface_client import detect_food_with_hf



# Portions typiques par catégorie DB (g par ingrédient dans un plat)
# Basées sur les recommandations ANSES / portions culinaires françaises standard
_CATEGORY_PORTIONS: dict[str, float] = {
    "MEAT":      150.0,  # viande, poisson, œufs (portion protéine standard)
    "DAIRY":      40.0,  # fromage, crème (accompagnement / garniture)
    "VEGETABLE": 120.0,  # légumes cuits ou crus
    "FRUIT":     100.0,  # fruit frais
    "GRAIN":     180.0,  # riz, pâtes, pain (cuits)
    "BEVERAGE":  200.0,  # boisson
    "SNACK":      30.0,  # noix, snack
    "OTHER":     100.0,  # défaut
}

# Mots-clés pour détecter garnitures/épices indépendamment de la catégorie DB
_GARNISH_KW = {
    "basil", "basilic", "parsley", "persil", "thyme", "thym", "oregano", "origan",
    "mint", "menthe", "tarragon", "estragon", "chive", "ciboulette", "rosemary",
    "romarin", "cilantro", "coriandre", "dill", "aneth", "sage", "sauge",
    "chervil", "cerfeuil",
}
_SAUCE_KW = {
    "sauce", "ketchup", "mayonnaise", "vinaigrette", "mustard", "moutarde",
    "gravy", "coulis", "dressing", "oil", "huile", "beurre", "butter",
}
_SPICE_KW = {
    "salt", "sel", "pepper", "poivre", "spice", "épice", "piment",
    "ginger", "gingembre", "cumin", "paprika", "curry", "cinnamon", "cannelle",
    "nutmeg", "muscade", "clove", "girofle", "anise", "anis",
}

# Sous-ensemble des condiments à traiter comme matière grasse : une portion d'huile
# ou de beurre (~1 c. à soupe) est bien plus petite qu'une portion de sauce.
_OIL_KW = {"oil", "huile", "beurre", "butter"}

# Mots-clés de rôle détectés dans la DESCRIPTION HuggingFace (fallback générique).
# Utilisés quand le nom du label seul ne suffit pas à identifier le rôle.
# Ex : "rosemary" inconnu → description "Fresh rosemary sprig used as garnish" → garnish
_DESC_GARNISH_KW: frozenset = frozenset({
    "garnish", "garnished", "garnishing", "sprig", "herb", "fresh herb", "decoration",
})
_DESC_OIL_KW: frozenset = frozenset({
    "drizzle", "drizzled", "drizzling",
})
_DESC_SAUCE_KW: frozenset = frozenset({
    "sauce", "dressing", "condiment",
})
_DESC_SPICE_KW: frozenset = frozenset({
    "seasoning", "seasoned", "sprinkled", "sprinkling", "pinch",
})

# Montants FIXES (en grammes) des éléments secondaires.
# Ils ne sont PAS mis à l'échelle : une pincée de sel ou un filet d'huile pèse
# pareil quelle que soit la taille de l'assiette.
_ROLE_FIXED_G: dict[str, float] = {
    "garnish": 5.0,   # herbes / garniture fraîche      → un brin
    "spice":   2.0,   # sel, poivre, épices sèches       → une pincée
    "oil":     12.0,  # huile / beurre / matière grasse  → ~1 c. à soupe
    "sauce":   30.0,  # sauce, condiment, dressing       → ~2 c. à soupe
}

# Bornes de sécurité appliquées à chaque quantité finale (g).
_MIN_GRAMS = 1.0
_MAX_GRAMS = 600.0


def _remove_sub_components(labels: list[dict]) -> list[dict]:
    """
    Supprime les labels qui sont des composants visuels d'un plat principal.

    Logique : on trie par score décroissant. Pour chaque label candidat,
    si son nom apparaît dans la description d'un label dominant déjà conservé,
    c'est un composant du plat principal → on le supprime.

    Exemple :
      - "pizza" (0.99, description: "...with mozzarella cheese, tomato sauce...")
      - "mozzarella cheese" (0.97) → "mozzarella cheese" est dans la description de pizza → supprimé
      - "tomato sauce"      (0.96) → "tomato sauce" est dans la description de pizza → supprimé
      - "basil"             (0.95) → "basil" est dans la description de pizza → supprimé

    Cas sains préservés :
      - "salmon" + "rice" + "broccoli" → aucun n'apparaît dans la description des autres → tous conservés
    """
    sorted_labels = sorted(labels, key=lambda x: float(x.get("score", 0)), reverse=True)
    kept: list[dict] = []
    for candidate in sorted_labels:
        candidate_name = candidate.get("label", "").lower()
        is_component = any(
            candidate_name in (dominant.get("description") or "").lower()
            for dominant in kept
        )
        if not is_component:
            kept.append(candidate)
    return kept


def _clamp(grams: float) -> float:
    """Borne une quantité dans [_MIN_GRAMS, _MAX_GRAMS]."""
    return max(_MIN_GRAMS, min(_MAX_GRAMS, grams))


def _clamp01(x: float) -> float:
    """Ramène une valeur dans [0, 1] (sécurise un score de confiance)."""
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _classify_role(label: str, description: str = "") -> str:
    """
    Classe un ingrédient détecté par son rôle dans l'assiette.

    Priorité 1 — mots-clés dans le nom du label (précision maximale).
    Priorité 2 — mots-clés de rôle dans la description HuggingFace (fallback générique).
                 Permet de détecter "rosemary" comme garnish si la description dit
                 "fresh rosemary sprig used as garnish", sans liste hardcodée.

    Renvoie l'un de : "garnish" | "spice" | "oil" | "sauce" | "main".
    """
    lbl  = (label or "").lower()
    desc = (description or "").lower()

    # Priorité 1 : nom du label
    if any(k in lbl for k in _GARNISH_KW):
        return "garnish"
    if any(k in lbl for k in _SAUCE_KW):
        return "oil" if any(k in lbl for k in _OIL_KW) else "sauce"
    if any(k in lbl for k in _SPICE_KW):
        return "spice"

    # Priorité 2 : description HuggingFace (fallback générique)
    if any(k in desc for k in _DESC_GARNISH_KW):
        return "garnish"
    if any(k in desc for k in _DESC_OIL_KW):
        return "oil"
    if any(k in desc for k in _DESC_SAUCE_KW):
        return "sauce"
    if any(k in desc for k in _DESC_SPICE_KW):
        return "spice"

    return "main"


def _estimate_portion(label: str, category: str | None = None) -> float:
    """
    Estimation absolue du poids d'un seul ingrédient (g).

    Priorité :
      1. Condiment (herbe / épice / huile / sauce) → montant fixe (_ROLE_FIXED_G)
      2. Sinon, portion typique de la catégorie DB  → _CATEGORY_PORTIONS
    """
    role = _classify_role(label)
    if role in _ROLE_FIXED_G:
        return _ROLE_FIXED_G[role]
    return _CATEGORY_PORTIONS.get((category or "OTHER").upper(), 100.0)


def _allocate_portions(matched: list[dict], portion_grams: int | None) -> None:
    """
    Attribue à chaque ingrédient un quantity_grams réaliste, en place.

    Deux modes selon portion_grams :
      - None (auto)  → priors ANSES absolus modulés par la confiance, pas de cible globale.
                       Robuste quand la taille du repas est inconnue.
      - int  (budget) → budget bidirectionnel : (portion_grams − condiments fixes) distribué
                        aux ingrédients principaux au prorata (catégorie × confiance).
                        Fonctionne dans les deux sens : 300 g comme 800 g donnent des
                        assiettes différentes et cohérentes. Les condiments restent fixes.
    """
    if not matched:
        return

    mains:   list[dict]  = []
    weights: list[float] = []
    fixed_total = 0.0

    # ── Étape 1 : condiments fixes + poids proportionnels des principaux ──────
    for ing in matched:
        label = ing.get("detected_label") or ing.get("name", "")
        role  = _classify_role(label, ing.get("hf_description", ""))
        if role in _ROLE_FIXED_G:
            ing["quantity_grams"] = _ROLE_FIXED_G[role]
            fixed_total += ing["quantity_grams"]
        else:
            cat  = (ing.get("category") or "OTHER").upper()
            base = _CATEGORY_PORTIONS.get(cat, 100.0)
            conf = _clamp01(float(ing.get("confidence", 0.0)))
            # Poids proportionnel : 0.75·base (conf=0) … 1.25·base (conf=1)
            mains.append(ing)
            weights.append(base * (0.75 + 0.5 * conf))

    if not mains:
        for ing in matched:
            ing["quantity_grams"] = _clamp(ing["quantity_grams"])
        return

    total_weight = sum(weights)

    if portion_grams is None:
        # ── Mode AUTO : priors absolus, pas de cible globale ─────────────────
        for ing, w in zip(mains, weights):
            ing["quantity_grams"] = round(w, 1)
    else:
        # ── Mode BUDGET : répartition bidirectionnelle ────────────────────────
        budget = float(portion_grams) - fixed_total
        budget = max(budget, _MIN_GRAMS * len(mains))  # garantie minimum
        if total_weight > 0:
            for ing, w in zip(mains, weights):
                ing["quantity_grams"] = round(budget * w / total_weight, 1)
        else:
            per_item = round(budget / len(mains), 1)
            for ing in mains:
                ing["quantity_grams"] = per_item

    # ── Étape 2 : bornes de sécurité finales ─────────────────────────────────
    for ing in matched:
        ing["quantity_grams"] = _clamp(ing["quantity_grams"])


async def run_analyze_food(image_bytes: bytes, filename: str | None) -> dict:
    """
    Vision brute : détecte les aliments sans calcul de macros.
    Retourne un dict conforme à AnalyzeFoodResponse.
    """
    try:
        predictions = await detect_food_with_hf(image_bytes)
        return {
            "status":         "success",
            "filename":       filename,
            "ai_predictions": predictions,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


async def run_analyze_meal(
    user_id:            str,
    meal_type:          Literal["breakfast", "lunch", "dinner", "snack"],
    images:             list[bytes],
    db:                 AsyncSession,
    portion_grams:      int | None = None,
    with_recommendation: bool = True,
    images_meta:        list[dict] | None = None,
) -> dict:
    """
    Pipeline complet : photo → identification → macros → recommandation IA.
    Retourne un dict conforme à AnalyzeMealResponse.

    Lève HTTPException pour :
      - 404 : utilisateur introuvable
      - 502 : service vision HuggingFace indisponible
      - 503 : erreur de persistance MongoDB
    """
    # ── 1. Profil utilisateur ─────────────────────────────────────────────────
    user = await queries.get_user_profile(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    # ── 2. Vision IA — détection sur chaque photo, fusion des labels ─────────────
    raw_labels: list[dict] = []
    try:
        for img in images:
            raw_labels += await detect_food_with_hf(img)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Service vision indisponible : {exc}")

    # Dédoublonnage : si même label détecté sur plusieurs photos, on garde la confiance max
    seen: dict[str, dict] = {}
    for lbl in raw_labels:
        key = lbl.get("label", "").lower()
        if key not in seen or lbl.get("score", 0) > seen[key].get("score", 0):
            seen[key] = lbl
    raw_labels = list(seen.values())

    confident_labels = [
        lbl for lbl in raw_labels
        if float(lbl.get("score", 0)) >= CONFIDENCE_THRESHOLD
    ]

    # ── 3b. Déduplication sémantique ─────────────────────────────────────────
    confident_labels = _remove_sub_components(confident_labels)

    # ── 3. Matching PostgreSQL ────────────────────────────────────────────────
    matched_raw: list[dict] = []
    not_found:   list[str]  = []

    for lbl in confident_labels:
        food_name  = lbl.get("label", "")
        ingredient = await queries.get_ingredient_by_name(db, food_name)
        if ingredient:
            ingredient["detected_label"]  = food_name
            ingredient["confidence"]      = float(lbl.get("score", 0))
            ingredient["hf_description"]  = lbl.get("description", "")
            matched_raw.append(ingredient)
        else:
            not_found.append(food_name)

    # Attribution réaliste des quantités : portions absolues par rôle/catégorie,
    # modulées par la confiance, avec portion_grams comme plafond.
    _allocate_portions(matched_raw, portion_grams)

    # ── 4. Calculs nutritionnels ──────────────────────────────────────────────
    meal_totals  = calculate_meal_totals(matched_raw)
    daily_needs  = compute_meal_needs(user)
    meal_balance = compute_meal_balance(meal_totals, daily_needs)

    # ── 5. Recommandation Ollama (non bloquant) ───────────────────────────────
    recommendation: str | None = None
    if with_recommendation:
        try:
            recommendation = await generate_meal_recommendation(user, meal_totals, daily_needs)
        except Exception:
            pass  # L'analyse reste valide sans recommandation

    # ── 6. Persistance MongoDB ────────────────────────────────────────────────
    analyzed_at = datetime.now(timezone.utc).isoformat()
    try:
        mongo_doc = {
            "user_id":    user_id,
            "meal_type":  meal_type,
            "analyzed_at": analyzed_at,
            "image_metadata": images_meta or [],
            "vision_result": {
                "provider":                  "huggingface",
                "labels_detected":           raw_labels,
                "confidence_threshold_used": CONFIDENCE_THRESHOLD,
            },
            "nutrition_result": {
                "ingredients_matched":   matched_raw,
                "ingredients_not_found": not_found,
                "meal_totals":           meal_totals,
            },
            "daily_needs":    daily_needs,
            "meal_balance":   meal_balance,
            "recommendation": recommendation,
        }
        analysis_id = await mongo.save_meal_analysis(mongo_doc)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Erreur persistance MongoDB : {exc}")

    # ── 7. Trace PostgreSQL (non bloquant) ────────────────────────────────────
    try:
        await queries.save_meal_to_postgres(
            db, user_id, int(meal_totals["calories"]), meal_totals
        )
    except Exception:
        pass  # Non bloquant : le document MongoDB est déjà persisté

    # ── 8. Construction de la réponse ─────────────────────────────────────────
    matched_for_response = [
        {
            "ingredient_id":  ing["ingredient_id"],
            "name":           ing["name"],
            "detected_label": ing["detected_label"],
            "confidence":     ing["confidence"],
            "quantity_grams": ing["quantity_grams"],
            "macros": {
                "calories":  round(_reliable_calories(ing) * ing["quantity_grams"] / 100, 2),
                "protein_g": round(float(ing["protein_g"])  * ing["quantity_grams"] / 100, 2),
                "carbs_g":   round(float(ing["carbs_g"])    * ing["quantity_grams"] / 100, 2),
                "fat_g":     round(float(ing["fat_g"])      * ing["quantity_grams"] / 100, 2),
                "fiber_g":   round(float(ing["fiber_g"])    * ing["quantity_grams"] / 100, 2),
            },
        }
        for ing in matched_raw
    ]

    return {
        "status":      "success",
        "analysis_id": analysis_id,
        "analyzed_at": analyzed_at,
        "meal_type":   meal_type,
        "vision": {
            "provider":                  "huggingface",
            "labels_detected":           raw_labels,
            "confidence_threshold_used": CONFIDENCE_THRESHOLD,
            "labels_count":              len(raw_labels),
        },
        "nutrition": {
            "ingredients_matched":   matched_for_response,
            "ingredients_not_found": not_found,
            "meal_totals":           meal_totals,
        },
        "daily_needs":    daily_needs,
        "meal_balance":   meal_balance,
        "recommendation": recommendation,
    }
