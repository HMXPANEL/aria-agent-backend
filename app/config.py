<<<<<<< HEAD
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AI Agent Brain"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # NVIDIA LLM Settings
    NVIDIA_API_KEY: str
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL_NAME: str = "meta/llama3-70b-instruct"

    # Android WebSocket Secret
    ANDROID_WEBSOCKET_SECRET: str = "your_android_secret_key"

    # Database Settings
    SQLITE_DB_PATH: str = "./data/memory.db"
    CHROMA_DB_PATH: str = "./data/chroma_db"

    # Agent Settings
    MAX_AGENT_ITERATIONS: int = 15
    AGENT_LOOP_INTERVAL_SEC: int = 1

settings = Settings()
=======
"""config.py - All settings from environment variables only."""
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("config")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
if not NVIDIA_API_KEY:
    raise ValueError("Missing env var: NVIDIA_API_KEY")

NVIDIA_BASE_URL  = "https://integrate.api.nvidia.com/v1"
LLM_PROVIDER     = os.getenv("LLM_PROVIDER",    "nvidia")
MODEL_AGENT      = os.getenv("MODEL_AGENT",      "meta/llama-3.1-70b-instruct")
MODEL_CHAT       = os.getenv("MODEL_CHAT",       "mistralai/mixtral-8x7b-instruct-v0.1")
MAX_RETRIES      = int(os.getenv("MAX_RETRIES",     "2"))
MAX_TOKENS       = int(os.getenv("MAX_TOKENS",      "1024"))
TEMPERATURE      = float(os.getenv("TEMPERATURE",   "0.15"))
MAX_LOOP_STEPS   = int(os.getenv("MAX_LOOP_STEPS",  "10"))
WS_TIMEOUT       = float(os.getenv("WS_TIMEOUT",    "120.0"))
PORT             = int(os.getenv("PORT",            "10000"))
HOST             = os.getenv("HOST",                "0.0.0.0")

# Built-in app map - longest keywords first for correct matching
APP_MAP = {
    "google maps":  "com.google.android.apps.maps",
    "play store":   "com.android.vending",
    "google pay":   "com.google.android.apps.nbu.paisa.user",
    "google meet":  "com.google.android.apps.meetings",
    "youtube":      "com.google.android.youtube",
    "whatsapp":     "com.whatsapp",
    "instagram":    "com.instagram.android",
    "telegram":     "org.telegram.messenger",
    "snapchat":     "com.snapchat.android",
    "facebook":     "com.facebook.katana",
    "twitter":      "com.twitter.android",
    "discord":      "com.discord",
    "linkedin":     "com.linkedin.android",
    "spotify":      "com.spotify.music",
    "netflix":      "com.netflix.mediaclient",
    "amazon":       "com.amazon.mShop.android.shopping",
    "flipkart":     "com.flipkart.android",
    "chrome":       "com.android.chrome",
    "gmail":        "com.google.android.gm",
    "photos":       "com.google.android.apps.photos",
    "camera":       "com.android.camera2",
    "calculator":   "com.android.calculator2",
    "calendar":     "com.google.android.calendar",
    "contacts":     "com.android.contacts",
    "settings":     "com.android.settings",
    "files":        "com.android.documentsui",
    "clock":        "com.android.deskclock",
    "maps":         "com.google.android.apps.maps",
    "phone":        "com.android.dialer",
    "dialer":       "com.android.dialer",
    "messages":     "com.google.android.apps.messaging",
    "music":        "com.google.android.music",
    "gpay":         "com.google.android.apps.nbu.paisa.user",
    "uber":         "com.ubercab",
    "zomato":       "app.zomato.in",
    "swiggy":       "in.swiggy.android",
    "paytm":        "net.one97.paytm",
    "reddit":       "com.reddit.frontpage",
    "x":            "com.twitter.android",
}

MESSAGING_APPS = {
    "com.whatsapp",
    "org.telegram.messenger",
    "com.facebook.katana",
    "com.instagram.android",
    "com.snapchat.android",
    "com.discord",
    "com.google.android.apps.messaging",
}

COMPLETION_SIGNALS = {
    "send_message": ["delivered", "sent", "tick", "check"],
    "open_app":     [],
    "search_web":   ["results", "http", "www"],
    "make_call":    ["calling", "ringing", "connected"],
}

logger.info(f"Config loaded | agent={MODEL_AGENT} | chat={MODEL_CHAT}")
>>>>>>> e389411 (Initial commit)
