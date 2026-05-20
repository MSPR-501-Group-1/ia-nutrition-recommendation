# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import generate, nutrition, health

app = FastAPI(
    title="HealthAI Coach - Nutrition IA API",
    description=(
        "Micro-service IA de recommandation nutritionnelle. "
        "Analyse des photos de repas, calcul des macros et génération "
        "de recommandations personnalisées via HuggingFace + Ollama."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production : URL exacte du frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(generate.router,   prefix="/api/v1", tags=["Vision IA"])
app.include_router(nutrition.router,  prefix="/api/v1", tags=["Nutrition"])
app.include_router(health.router,     prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "HealthAI Coach — API IA Nutrition en ligne.",
        "docs":    "/docs",
        "health":  "/api/v1/health",
    }