from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- HuggingFace ---
    huggingface_api_key: str
    hf_food_model_url: str = "https://api-inference.huggingface.co/models/nateraw/food"

    # --- PostgreSQL ---
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "healthai"
    db_user: str = "postgres"
    db_password: str = ""

    # --- MongoDB ---
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "healthai_ia"

    # --- Ollama ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()