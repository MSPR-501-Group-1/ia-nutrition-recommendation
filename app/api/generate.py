from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.vision.huggingface_client import detect_food_with_hf

router = APIRouter()


@router.post("/analyze-food", tags=["Vision IA"])
async def analyze_food(file: UploadFile = File(...)):
    """
    Reçoit une image, l'envoie au modèle vision IA (Kimi-K2.5 via HuggingFace)
    et retourne la liste brute des aliments détectés avec leur score de confiance.
    Pour le pipeline complet (vision + nutrition + MongoDB), utiliser
    POST /users/{user_id}/analyze-meal.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image.")

    try:
        image_bytes = await file.read()
        predictions = await detect_food_with_hf(image_bytes)
        return {
            "status":         "success",
            "filename":       file.filename,
            "ai_predictions": predictions,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))