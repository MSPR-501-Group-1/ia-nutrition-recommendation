# app/api/generate.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.vision.huggingface_client import detect_food_with_hf

# On crée un "routeur" (un mini-serveur qu'on branchera au grand tout à l'heure)
router = APIRouter()

@router.post("/analyze-food")
async def analyze_food(file: UploadFile = File(...)):
    """
    Reçoit une image depuis le front-end, l'envoie à l'IA et renvoie les résultats.
    """
    # 1. Vérification de sécurité basique (est-ce bien une image ?)
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Le fichier doit être une image.")

    try:
        # 2. On lit l'image en mémoire (format bytes)
        image_bytes = await file.read()
        
        # 3. On fait LE VRAI APPEL à Hugging Face !
        predictions = await detect_food_with_hf(image_bytes)
        
        # 4. On renvoie le résultat propre
        return {
            "status": "success",
            "filename": file.filename,
            "ai_predictions": predictions
        }
        
    except Exception as e:
        # Si Hugging Face plante ou que la clé est mauvaise, on renvoie une belle erreur HTTP
        raise HTTPException(status_code=500, detail=str(e))