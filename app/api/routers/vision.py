# app/api/routers/vision.py
# Déclarations de routes Vision IA — aucune logique métier ici.
# Toute la logique du pipeline est dans :
#   app/services/vision/analyze_meal_service.py

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.meal_analysis import AnalyzeFoodResponse, AnalyzeMealResponse
from app.services.vision.analyze_meal_service import run_analyze_food, run_analyze_meal

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# POST /analyze-food — Vision brute (debug / test partiel)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/analyze-food", response_model=AnalyzeFoodResponse, tags=["Vision IA"])
async def analyze_food(file: UploadFile = File(...)):
    """
    Retourne la liste brute des aliments détectés par HuggingFace, sans calcul de macros.
    Pour le pipeline complet (vision + macros + recommandation), utiliser
    POST /users/{user_id}/analyze-meal.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image.")
    return await run_analyze_food(await file.read(), file.filename)


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
    user_id:   str,
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] = "lunch",
    file:      UploadFile = File(...),
    db:        AsyncSession = Depends(get_db),
):
    """
    **Pipeline complet d'analyse d'un repas photographié.**

    **Étapes exécutées :**
    1. Validation de l'image et de l'utilisateur (PostgreSQL)
    2. Détection des aliments via HuggingFace Kimi-K2.5 (vision multimodale)
    3. Filtrage par seuil de confiance (≥ 0.40)
    4. Matching de chaque aliment dans PostgreSQL → récupération des macros
    5. Calcul des totaux du repas + besoins journaliers (Mifflin-St Jeor)
    6. Génération d'une recommandation personnalisée via Ollama (non bloquant)
    7. Persistance du document complet dans MongoDB (`meal_analyses`)
    8. Trace légère dans PostgreSQL (`meal` table)

    **Contrat de réponse :** `AnalyzeMealResponse` (voir `app/models/meal_analysis.py`)

    `recommendation` peut être `null` si Ollama est indisponible — les autres
    champs sont toujours présents.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image.")
    return await run_analyze_meal(user_id, meal_type, await file.read(), db)
