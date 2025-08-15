from fastapi import APIRouter, UploadFile, File, HTTPException, Path
from typing import Any, Dict

from models.schemas import TextInput
from services import stt, llm, tts
from storage.history import get_history, get_lock, append_and_persist, chat_history_store
from utils.text import SYSTEM_INSTRUCTIONS, FALLBACK_MESSAGE
from config import get_settings

_settings = get_settings()
router = APIRouter()

@router.post("/generate")
async def generate_tts(data: TextInput):
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    # Limit TTS length
    if len(text) > _settings.TTS_CHAR_LIMIT:
        text = text[:_settings.TTS_CHAR_LIMIT].rsplit(" ", 1)[0] + "..."
    try:
        audio_url = await tts.speak(text)
        return {"audio_url": audio_url}
    except Exception:
        # Don't leak vendor errors
        raise HTTPException(status_code=502, detail="TTS service unavailable")

@router.get("/agent/history/{session_id}")
async def fetch_history(session_id: str = Path(...)):
    hist = await get_history(session_id)
    return {"session_id": session_id, "messages": hist}

@router.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str = Path(...), audio: UploadFile = File(...)):
    # 1) STT outside session lock
    try:
        user_text = await stt.transcribe_uploadfile_to_text(audio)
    except Exception:
        hist = await get_history(session_id)
        return {
            "session_id": session_id,
            "error": "STT failed",
            "transcribed_text": "",
            "llm_response": FALLBACK_MESSAGE,
            "audio_url": await tts.get_fallback_audio_url(),
            "history": hist,
        }

    # 2) Consistent LLM + history under lock
    lock = get_lock(session_id)
    async with lock:
        existing = await get_history(session_id)

        try:
            ai_text = await llm.generate_reply(existing, user_text, SYSTEM_INSTRUCTIONS)
            if not ai_text:
                ai_text = FALLBACK_MESSAGE
        except Exception:
            ai_text = FALLBACK_MESSAGE

        # Clip TTS text
        if len(ai_text) > _settings.TTS_CHAR_LIMIT:
            ai_text = ai_text[:_settings.TTS_CHAR_LIMIT].rsplit(" ", 1)[0] + "..."

        # Persist both messages
        new_hist = await append_and_persist(session_id, [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": ai_text},
        ])

    # 3) TTS (outside lock)
    audio_url = await tts.speak_or_fallback(ai_text)

    return {
        "session_id": session_id,
        "transcribed_text": user_text,
        "llm_response": ai_text,
        "audio_url": audio_url,
        "history": new_hist,
    }