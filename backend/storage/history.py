import os
import re
import json
import asyncio
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any

from config import get_settings

_settings = get_settings()

chat_history_store: dict[str, list[Dict[str, Any]]] = defaultdict(list)
_session_locks: dict[str, asyncio.Lock] = {}

def _safe_session_id(sid: str) -> str:
    sid = (sid or "").strip()
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", sid)
    return safe[:120] or "session"

def _history_path(session_id: str) -> str:
    return os.path.join(_settings.CHAT_HISTORY_DIR, f"{_safe_session_id(session_id)}.json")

def _trim(messages: list[Dict[str, str]]) -> list[Dict[str, str]]:
    limit = _settings.CHAT_HISTORY_LIMIT
    if limit and len(messages) > limit:
        return messages[-limit:]
    return messages

def get_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock

async def load_history(session_id: str) -> list[Dict[str, str]]:
    path = _history_path(session_id)
    def _read():
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "messages" in data:
            return data.get("messages", [])
        if isinstance(data, list):
            return data
        return []
    return await asyncio.to_thread(_read)

async def save_history(session_id: str, messages: list[Dict[str, str]]) -> None:
    path = _history_path(session_id)
    def _write():
        payload = {
            "session_id": session_id,
            "messages": messages,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    await asyncio.to_thread(_write)

async def get_history(session_id: str) -> list[Dict[str, str]]:
    hist = chat_history_store.get(session_id)
    if not hist:
        hist = await load_history(session_id)
        chat_history_store[session_id] = hist
    return hist

async def append_and_persist(session_id: str, new_messages: list[Dict[str, str]]) -> list[Dict[str, str]]:
    hist = chat_history_store.get(session_id) or await load_history(session_id)
    hist = list(hist)
    hist.extend(new_messages)
    hist = _trim(hist)
    chat_history_store[session_id] = hist
    await save_history(session_id, hist)
    return hist