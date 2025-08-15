import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Required API Keys
    MURF_API_KEY: str
    ASSEMBLY_AI: str
    GEMINI_API_KEY: str

    # Optional configs with sensible defaults
    CHAT_HISTORY_DIR: str = os.getenv("CHAT_HISTORY_DIR", "data/history")
    CHAT_HISTORY_LIMIT: int = int(os.getenv("CHAT_HISTORY_LIMIT", "200"))
    CORS_ALLOW_ORIGINS: list[str] = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    VOICE_ID: str = os.getenv("VOICE_ID", "en-US-terrell")

    # LLM and prompt limits
    LLM_MODEL: str = os.getenv("LLM_MODEL", "models/gemini-1.5-flash")
    PROMPT_CHAR_BUDGET: int = int(os.getenv("PROMPT_CHAR_BUDGET", "12000"))
    TTS_CHAR_LIMIT: int = int(os.getenv("TTS_CHAR_LIMIT", "1200"))

    def __init__(self):
        self.MURF_API_KEY = os.getenv("MURF_API_KEY", "")
        self.ASSEMBLY_AI = os.getenv("ASSEMBLY_AI", "")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

        if not self.MURF_API_KEY or not self.ASSEMBLY_AI or not self.GEMINI_API_KEY:
            raise RuntimeError("Missing one or more API keys: MURF_API_KEY, ASSEMBLY_AI, GEMINI_API_KEY")

        os.makedirs(self.CHAT_HISTORY_DIR, exist_ok=True)

@lru_cache()
def get_settings() -> Settings:
    return Settings()