# app/services/vision/vision_orchestrator.py
# Orchestre : détection via HuggingFace → matching dans PostgreSQL.

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.vision.huggingface_client import detect_food_with_hf
from app.db import queries


_CONFIDENCE_THRESHOLD = 0.40  # Labels en dessous de ce seuil sont ignorés


async def analyze_image_and_match_ingredients(
    image_bytes: bytes,
    db: AsyncSession,
) -> dict:
    """
    Pipeline complet image → ingrédients PostgreSQL :
    1. Envoie l'image à HuggingFace (Kimi-K2.5) et récupère les labels.
    2. Filtre les labels sous le seuil de confiance.
    3. Pour chaque label, cherche l'ingrédient correspondant dans PostgreSQL.
    4. Retourne matched / not_found séparément.

    Retour :
    {
        "provider": "huggingface",
        "labels_detected": [...],
        "confidence_threshold_used": 0.40,
        "ingredients_matched": [...],
        "ingredients_not_found": [...],
    }
    """
    # Étape 1 — Vision IA
    labels: list[dict] = await detect_food_with_hf(image_bytes)

    # Étape 2 — Filtrage par confiance
    confident_labels = [
        lbl for lbl in labels if float(lbl.get("score", 0)) >= _CONFIDENCE_THRESHOLD
    ]

    # Étape 3 — Matching PostgreSQL
    matched: list[dict] = []
    not_found: list[str] = []

    for label_item in confident_labels:
        food_name = label_item.get("label", "")
        ingredient = await queries.get_ingredient_by_name(db, food_name)

        if ingredient:
            ingredient["detected_label"] = food_name
            ingredient["confidence"]     = float(label_item.get("score", 0))
            ingredient["quantity_grams"] = 100  # quantité par défaut : 100 g
            matched.append(ingredient)
        else:
            not_found.append(food_name)

    return {
        "provider":                   "huggingface",
        "labels_detected":            labels,
        "confidence_threshold_used":  _CONFIDENCE_THRESHOLD,
        "ingredients_matched":        matched,
        "ingredients_not_found":      not_found,
    }
