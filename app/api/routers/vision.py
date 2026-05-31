# app/api/routers/vision.py
# Déclarations de routes Vision IA — aucune logique métier ici.
# Toute la logique du pipeline est dans :
#   app/services/vision/analyze_meal_service.py

from typing import List, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.meal_analysis import AnalyzeFoodResponse, AnalyzeMealResponse
from app.services.vision.analyze_meal_service import run_analyze_food, run_analyze_meal

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# POST /analyze-food — Vision brute (debug / test partiel)
# [HORS SUJET — commenté pour l'évaluation]
# ─────────────────────────────────────────────────────────────────────────────

# @router.post("/analyze-food", response_model=AnalyzeFoodResponse, tags=["Vision IA"])
# async def analyze_food(file: UploadFile = File(...)):
#     """
#     Retourne la liste brute des aliments détectés par HuggingFace, sans calcul de macros.
#     Pour le pipeline complet (vision + macros + recommandation), utiliser
#     POST /users/{user_id}/analyze-meal.
#     """
#     if not file.content_type or not file.content_type.startswith("image/"):
#         raise HTTPException(status_code=400, detail="Le fichier doit être une image.")
#     return await run_analyze_food(await file.read(), file.filename)


# ─────────────────────────────────────────────────────────────────────────────
# POST /users/{user_id}/analyze-meal — Pipeline complet (cœur du sujet MSPR)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/users/{user_id}/analyze-meal",
    response_model=AnalyzeMealResponse,
    response_model_exclude_none=True,
    summary="Pipeline complet : photo → identification → macros → recommandation IA",
    tags=["Vision IA"],
    responses={
        400: {"description": "Fichier non valide (pas une image)"},
        404: {"description": "Utilisateur introuvable"},
        502: {"description": "Service vision HuggingFace indisponible"},
        503: {"description": "Erreur de persistance MongoDB"},
    },
)
async def analyze_meal(
    user_id:             str,
    meal_type:           Literal["breakfast", "lunch", "dinner", "snack"] = Form("lunch"),
    portion_grams:       int | None = None,
    with_recommendation: bool = True,
    file:                UploadFile | None = File(None),
    files:               List[UploadFile] = File(default=[]),
    db:                  AsyncSession = Depends(get_db),
):
    """
    **Pipeline complet d'analyse d'un repas photographié.**

    Accepte **1 ou plusieurs photos** (ex : plat principal + accompagnement).
    Rétrocompatible : `file` (champ unique) et `files` (liste) sont tous les deux acceptés.
    Les labels détectés sur toutes les photos sont fusionnés avant analyse.

    **Étapes exécutées :**
    1. Validation des images et de l'utilisateur (PostgreSQL)
    2. Détection des aliments via HuggingFace sur chaque photo
    3. Fusion des labels (dédoublonnage par label, confiance max conservée)
    4. Matching dans PostgreSQL → macros
    5. Calcul des totaux + besoins journaliers (Mifflin-St Jeor)
    6. Recommandation personnalisée via Ollama (non bloquant)
    7. Persistance MongoDB + trace PostgreSQL
    """
    # Fusion des deux paramètres pour rétrocompatibilité
    all_files = list(files)
    if file is not None:
        all_files.append(file)

    if not all_files:
        raise HTTPException(status_code=400, detail="Au moins une image est requise.")
    if portion_grams is not None and (portion_grams < 50 or portion_grams > 5000):
        raise HTTPException(status_code=400, detail="portion_grams doit être entre 50 et 5000 g.")

    images: list[bytes] = []
    images_meta: list[dict] = []
    for f in all_files:
        if not f.content_type or not f.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"{f.filename} : le fichier doit être une image.")
        data = await f.read()
        images.append(data)
        images_meta.append({
            "filename":     f.filename or "unknown",
            "content_type": f.content_type,
            "size_bytes":   len(data),
        })

    return await run_analyze_meal(
        user_id, meal_type, images, db, portion_grams, with_recommendation,
        images_meta=images_meta,
    )
