import os
from dotenv import load_dotenv
from model_config import MODEL_CHOICES

load_dotenv()


class Config:
    """Application configuration settings."""

    # API Keys
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    SEC_IDENTITY = os.getenv("SEC_IDENTITY", "Agent user@example.com")

    # Application Settings
    DB_PATH = os.getenv("DB_PATH", "data/alpha_scout.db")
    ALLOWED_EMAILS = {
        email.strip().lower()
        for email in os.getenv("ALLOWED_EMAILS", "").split(",")
        if email.strip()
    }

    # Streamlit Page Configuration
    PAGE_TITLE = "Market Intelligence"
    PAGE_ICON = "📊"
    LAYOUT = "wide"

    # Available AI Models
    AVAILABLE_MODELS = MODEL_CHOICES
    DEFAULT_MODEL = MODEL_CHOICES[0]

    # Cache Configuration
    STOCK_DATA_TTL = 3600

    @classmethod
    def available_models(cls):
        from model_config import provider_for_model
        keys = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GOOGLE_API_KEY"}
        return [m for m in MODEL_CHOICES if os.getenv(keys[provider_for_model(m)])]

    @classmethod
    def validate(cls):
        if not cls.available_models():
            raise ValueError("Configure at least one AI provider API key")
        return True
