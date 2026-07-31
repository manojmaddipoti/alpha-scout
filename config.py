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
    def validate(cls):
        """Validate that required configuration is present."""
        required = {
            "ANTHROPIC_API_KEY": cls.ANTHROPIC_API_KEY,
            "OPENAI_API_KEY": cls.OPENAI_API_KEY,
            "GOOGLE_API_KEY": cls.GOOGLE_API_KEY,
            "TAVILY_API_KEY": cls.TAVILY_API_KEY,
        }

        missing = [key for key, value in required.items() if not value]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return True
