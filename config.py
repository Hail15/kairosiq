# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:

    # --- App ---
    APP_NAME: str = os.getenv("APP_NAME", "KairosIQ")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # --- Database ---
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # --- Gmail ---
    GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
    ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")

    # --- Anthropic (Claude AI) ---
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # --- Alpha Vantage (Asset Prices) ---
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")

    # --- Kalshi ---
    KALSHI_API_KEY: str = os.getenv("KALSHI_API_KEY", "")
    KALSHI_PRIVATE_KEY: str = os.getenv("KALSHI_PRIVATE_KEY", "")

    # --- Metaculus ---
    METACULUS_API_TOKEN: str = os.getenv("METACULUS_API_TOKEN", "")

    # --- Signal Detection Settings ---
    SIGNAL_THRESHOLD: float = float(os.getenv("SIGNAL_THRESHOLD", "8.0"))
    SIGNAL_DECAY_HOURS: int = int(os.getenv("SIGNAL_DECAY_HOURS", "72"))
    POLLING_INTERVAL_MINUTES: int = 15
    HIGH_CONFIDENCE_THRESHOLD: float = 15.0
    MEDIUM_CONFIDENCE_THRESHOLD: float = 8.0

    def validate(self):
        required = {
            "DATABASE_URL": self.DATABASE_URL,
            "ANTHROPIC_API_KEY": self.ANTHROPIC_API_KEY,
            "GMAIL_ADDRESS": self.GMAIL_ADDRESS,
            "GMAIL_APP_PASSWORD": self.GMAIL_APP_PASSWORD,
        }
        missing = [key for key, val in required.items() if not val]
        if missing:
            print(f"⚠️  WARNING: Missing environment variables: {missing}")
            print("   Fill these in your .env file before running the full system.")
        else:
            print("✅ All critical environment variables loaded.")

# Single instance used everywhere
settings = Settings()