# main.py
import socket
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers import vision, nutrition
from app.api import health

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
app.include_router(vision.router,     prefix="/api/v1", tags=["Vision IA"])
app.include_router(nutrition.router,  prefix="/api/v1", tags=["Nutrition"])
app.include_router(health.router,     prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "HealthAI Coach — API IA Nutrition en ligne.",
        "docs":    "/docs",
        "health":  "/api/v1/health",
    }


def _find_free_port(preferred: int) -> int:
    """Retourne `preferred` s'il est libre, sinon un port libre aléatoire."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    port = _find_free_port(8001)
    if port != 8001:
        print(f"[warn] port 8001 occupé, démarrage sur le port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)