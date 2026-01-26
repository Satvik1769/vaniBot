"""Application configuration."""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Battery Smart Voicebot API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:1234@localhost:5432/postgres"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # API Keys
    DEEPGRAM_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # Amazon Connect
    AWS_REGION: str = "ap-southeast-1"
    CONNECT_INSTANCE_ID: Optional[str] = None
    CONNECT_CONTACT_FLOW_ID: Optional[str] = None
    CONNECT_QUEUE_ID: Optional[str] = None

    # Voice Settings
    DEFAULT_LANGUAGE: str = "hi-en"
    STT_MODEL: str = "nova-2"
    TTS_VOICE_HINDI: str = "aura-asteria-hi"
    TTS_VOICE_ENGLISH: str = "aura-asteria-en"

    # Confidence Thresholds
    CONFIDENCE_HIGH: float = 0.85
    CONFIDENCE_MEDIUM: float = 0.60
    CONFIDENCE_LOW: float = 0.45
    CONFIDENCE_CRITICAL: float = 0.30

    # Sentiment Thresholds
    SENTIMENT_POSITIVE: float = 0.3
    SENTIMENT_NEUTRAL: float = -0.2
    SENTIMENT_NEGATIVE: float = -0.5
    SENTIMENT_CRITICAL: float = -0.7

    # ✅ THIS IS THE CORRECT CONFIG FOR SETTINGS
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"   # allow undeclared env vars
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
