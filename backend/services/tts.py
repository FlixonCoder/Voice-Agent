import asyncio
from typing import Optional
from murf import Murf

from config import get_settings
from utils.text import FALLBACK_MESSAGE

_settings = get_settings()
_murf = Murf(api_key=_settings.MURF_API_KEY)

_fallback_cached: Optional[str] = None

async def speak(text: str) -> str:
    """
    Generate TTS from Murf and return the audio URL.
    """
    def _call():
        return _murf.text_to_speech.generate(
            text=text,
            voice_id=_settings.VOICE_ID
        )
    res = await asyncio.to_thread(_call)
    return res.audio_file

async def get_fallback_audio_url() -> str:
    """
    Cache a fallback audio clip to avoid repeated Murf calls during failures.
    """
    global _fallback_cached
    if _fallback_cached:
        return _fallback_cached
    try:
        _fallback_cached = await speak(FALLBACK_MESSAGE)
    except Exception:
        # Final fallback: return a safe placeholder (client should handle)
        _fallback_cached = "about:blank"
    return _fallback_cached

async def speak_or_fallback(text: str) -> str:
    try:
        return await speak(text)
    except Exception:
        return await get_fallback_audio_url()