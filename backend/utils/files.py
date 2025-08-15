import asyncio
import shutil
import tempfile
from fastapi import UploadFile

async def upload_to_tempfile(upload: UploadFile, suffix: str = ".wav") -> str:
    def _write():
        upload.file.seek(0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(upload.file, tmp)
            return tmp.name
    return await asyncio.to_thread(_write)