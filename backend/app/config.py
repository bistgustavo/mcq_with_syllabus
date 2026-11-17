"""Application settings.

Every value is read from the environment (or the ``.env`` file in the backend
folder). Nothing is hard-coded: services must always go through ``settings``.
"""

from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the MCQ platform backend."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Infrastructure ----------------------------------------------------
    DATABASE_URL: str
    # Cloud endpoints are tried first; the *_LOCAL_URL ones are used when the
    # cloud is unreachable. Set a *_LOCAL_URL to "" to disable that fallback.
    QDRANT_URL: str
    QDRANT_API_KEY: str = ""
    QDRANT_LOCAL_URL: str = "http://localhost:6333"
    REDIS_URL: str
    REDIS_LOCAL_URL: str = "redis://localhost:6379/0"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # --- LLM providers -----------------------------------------------------
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    # Tried in this order. Cloud first (fast); local Ollama takes over when the
    # cloud APIs hit their rate limits or are down.
    LLM_PROVIDER_ORDER: str = "groq,gemini,ollama"
    OLLAMA_MODEL: str = "mistral:7b"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_FALLBACK_MODEL: str = "openai/gpt-oss-20b"  # separate rate limit on Groq
    GEMINI_MODEL: str = "gemini-flash-latest"
    # How long a provider is skipped after a failure / after a rate-limit (429).
    PROVIDER_COOLDOWN_SECONDS: int = 120
    RATE_LIMIT_COOLDOWN_SECONDS: int = 900
    OLLAMA_TIMEOUT: int = 180  # seconds for the generation call; connect timeout is 5s
    CLOUD_TIMEOUT: int = 60  # seconds for Groq / Gemini calls

    # --- Auth ----------------------------------------------------------------
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24
    # Comma separated e-mails that are always admins. When empty, the first
    # account ever registered becomes the admin.
    ADMIN_EMAILS: str = ""

    # --- HTTP ----------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Uploads / retrieval / generation -------------------------------------
    UPLOAD_DIR: str = "uploads"  # relative to the backend working directory
    MAX_UPLOAD_MB: int = 25
    MAX_PRIOR_QUESTIONS: int = 30
    RETRIEVAL_TOP_K: int = 6
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    SEARCH_BACKENDS: str = "bing,yandex,duckduckgo"  # web research, tried in order (Wikipedia is the final fallback)
    QDRANT_COLLECTION: str = "syllabus_chunks"

    LOG_LEVEL: str = "INFO"
    APP_ENV: str = "development"  # "production" enables strict checks and HSTS

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("prod", "production")

    @cached_property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @cached_property
    def provider_order(self) -> list[str]:
        known = ("groq", "gemini", "ollama")
        order = [p.strip().lower() for p in self.LLM_PROVIDER_ORDER.split(",") if p.strip().lower() in known]
        return order or list(known)

    @cached_property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}


settings = Settings()
