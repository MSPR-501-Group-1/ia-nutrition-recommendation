# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Pydantic va chercher automatiquement HUGGINGFACE_API_KEY dans le .env
    huggingface_api_key: str 
    
    # URL d'un très bon modèle gratuit pour la nourriture sur Hugging Face
    hf_food_model_url: str = "https://api-inference.huggingface.co/models/nateraw/food"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# On instancie les settings une seule fois pour toute l'application
    # --- Base de données PostgreSQL (ETL MSPR 1) ---
    # Ces variables doivent être dans ton .env
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "healthai"
    db_user: str = "postgres"
    db_password: str = ""
 
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
 
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
settings = Settings()