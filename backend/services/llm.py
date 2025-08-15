import asyncio
from typing import List, Dict, Any
from google import genai

from config import get_settings
from utils.text import SYSTEM_INSTRUCTIONS

_settings = get_settings()
_client = genai.Client(api_key=_settings.GEMINI_API_KEY)

def _map_role(role: str) -> str:
    # Google GenAI expects "user" and "model"
    if role == "assistant":
        return "model"
    if role == "user":
        return "user"
    return role or "user"

def build_prompt_contents(history: List[Dict[str, str]], user_text: str, budget: int) -> list[dict]:
    """
    Build Gemini 'contents' with a rough char budget.
    Includes as much recent history as fits, plus the new user message.
    """
    parts: list[dict] = []
    total = 0
    # Pack from end backwards (most recent first)
    for m in reversed(history):
        role = _map_role(m.get("role", "user"))
        content = (m.get("content") or "")[:budget]  # hard clip per message
        chunk_len = len(content) + 10
        if total + chunk_len > budget:
            break
        parts.append({"role": role, "parts": [{"text": content}]})
        total += chunk_len
    parts.reverse()
    # Append the new user message last
    parts.append({"role": "user", "parts": [{"text": user_text}]})
    return parts

async def generate_reply(history: List[Dict[str, str]], user_text: str, system_instructions: str | None = None) -> str:
    contents = build_prompt_contents(history, user_text, _settings.PROMPT_CHAR_BUDGET)
    sys_inst = system_instructions or SYSTEM_INSTRUCTIONS

    def _call():
        return _client.models.generate_content(
            model=_settings.LLM_MODEL,
            contents=contents,
            system_instruction=sys_inst
        )
    resp = await asyncio.to_thread(_call)
    text = (getattr(resp, "text", None) or "").strip()
    return text