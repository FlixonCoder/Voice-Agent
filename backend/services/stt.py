import asyncio
import os
from typing import Optional
import assemblyai as aai

from config import get_settings
from utils.files import upload_to_tempfile

_settings = get_settings()
aai.settings.api_key = _settings.ASSEMBLY_AI

async def transcribe_uploadfile_to_text(upload) -> str:
    """
    Writes the UploadFile to a temp file and transcribes it.
    Returns the transcribed text (stripped). Raises on hard failures.
    """
    temp_path = await upload_to_tempfile(upload, suffix=os.path.splitext(upload.filename or "")[-1] or ".wav")
    try:
        # Run STT in thread (SDK is sync)
        def _call():
            transcriber = aai.Transcriber()
            return transcriber.transcribe(temp_path)
        transcript = await asyncio.to_thread(_call)

        text = (getattr(transcript, "text", "") or "").strip()
        if not text:
            raise ValueError("No speech detected in audio.")
        return text
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass