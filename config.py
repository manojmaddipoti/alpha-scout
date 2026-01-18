import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration settings."""

    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    SEC_IDENTITY = os.getenv("SEC_IDENTITY", "Agent user@example.com")

    # Application Settings
    APP_PASSWORD = os.getenv("APP_PASSWORD", "Laxmi@2026")
    DB_PATH = os.getenv("DB_PATH", "/tmp/data/chat_history.db")

    # Streamlit Page Configuration
    PAGE_TITLE = "Market Intelligence"
    PAGE_ICON = "📊"
    LAYOUT = "wide"

    # Available AI Models
    AVAILABLE_MODELS = [
        "gpt-4o",
        "gemini-3-pro-preview",
        "deep-research-pro-preview-12-2025"
    ]
    DEFAULT_MODEL = "gemini-3-pro-preview"

    # Cache Configuration
    STOCK_DATA_TTL = 3600  # 1 hour in seconds

    @classmethod
    def validate(cls):
        """Validate that required configuration is present."""
        required = {
            "OPENAI_API_KEY": cls.OPENAI_API_KEY,
            "GOOGLE_API_KEY": cls.GOOGLE_API_KEY,
            "TAVILY_API_KEY": cls.TAVILY_API_KEY,
        }

        missing = [key for key, value in required.items() if not value]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return True
