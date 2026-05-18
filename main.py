# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import generate

# On initialise l'application
app = FastAPI(
    title="HealthAI Coach - Nutrition API",
    description="API IA pour la recommandation nutritionnelle et l'analyse d'images.",
    version="1.0.0"
)

# Configuration CORS (Indispensable pour que ton futur frontend puisse parler à cette API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En production, on mettra l'URL exacte du frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# On branche notre routeur d'analyse d'image créé à l'étape 2
app.include_router(generate.router, prefix="/api/v1", tags=["Vision IA"])

@app.get("/")
async def root():
    return {"message": "Bienvenue sur l'API IA de HealthAI Coach. L'API est en ligne !"}