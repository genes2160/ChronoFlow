from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    APP_NAME: str = "ChronoFlow"

    ENV: str = "poc"  # poc | dev | prod

    ORGANIZED_DATA_DIR: Path = Path("data/organized")
    RAW_DATA_DIR: Path = Path("data/raw")

    SQLITE_DB: str = "sqlite:///./chronoflow.db"
    POSTGRES_DB_ADDRESS: str | None = None

    LLM_PROVIDER: str = "groq"
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    JINA_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    
    RUNNER_SCRIPT: str = "runner.py"
    LLM_RUNNER_SCRIPT: str = "llm_runner.py"
    
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True

    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    @property
    def DATABASE_URL(self) -> str:
        if self.ENV in ["poc", "local"]:
            return self.SQLITE_DB

        if self.ENV in ["dev", "prod"]:
            if not self.POSTGRES_DB_ADDRESS:
                raise ValueError("POSTGRES_DB_ADDRESS must be set for dev/prod")
            return self.POSTGRES_DB_ADDRESS

        raise ValueError(f"Unknown ENV: {self.ENV}")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()