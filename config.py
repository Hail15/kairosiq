# config.py
import os
from dotenv import load_dotenv

load_dotenv()

def get_setting(key, default=""):
    """
    Get a setting from environment variables or Streamlit secrets.
    Works both locally and on Streamlit Cloud.
    """
    # Try environment variable first
    val = os.getenv(key, "")
    if val:
        return val

    # Try Streamlit secrets
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
        return default
    except Exception:
        return default

class Settings:

    # --- App ---
    APP_NAME: str = get_setting("APP_NAME", "KairosIQ")
    ENVIRONMENT: str = get_setting("ENVIRONMENT", "development")

    # --- Database ---
    SUPABASE_URL: str = get_setting("SUPABASE_URL")
    SUPABASE_KEY: str = get_setting("SUPABASE_KEY")
    DATABASE_URL: str = get_setting("DATABASE_URL")

    # --- Gmail ---
    GMAIL_ADDRESS: str = get_setting("GMAIL_ADDRESS")
    GMAIL_APP_PASSWORD: str = get_setting("GMAIL_APP_PASSWORD")
    ALERT_EMAIL_TO: str = get_setting("ALERT_EMAIL_TO")

    # --- Anthropic ---
    ANTHROPIC_API_KEY: str = get_setting("ANTHROPIC_API_KEY")

    # --- Alpha Vantage ---
    ALPHA_VANTAGE_API_KEY: str = get_setting("ALPHA_VANTAGE_API_KEY")

    # --- Kalshi ---
    KALSHI_API_KEY: str = get_setting("KALSHI_API_KEY")
    KALSHI_PRIVATE_KEY: str = get_setting("KALSHI_PRIVATE_KEY")

    # --- Metaculus ---
    METACULUS_API_TOKEN: str = get_setting("METACULUS_API_TOKEN")

    # --- Alpaca ---
    ALPACA_PAPER_KEY:    str = get_setting("ALPACA_PAPER_KEY")
    ALPACA_PAPER_SECRET: str = get_setting("ALPACA_PAPER_SECRET")
    ALPACA_LIVE_KEY:     str = get_setting("ALPACA_LIVE_KEY")
    ALPACA_LIVE_SECRET:  str = get_setting("ALPACA_LIVE_SECRET")

    # --- Signal Detection ---
    SIGNAL_THRESHOLD: float = float(get_setting("SIGNAL_THRESHOLD", "8.0"))
    SIGNAL_DECAY_HOURS: int = int(get_setting("SIGNAL_DECAY_HOURS", "72"))
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
        else:
            print("✅ All critical environment variables loaded.")

settings = Settings()