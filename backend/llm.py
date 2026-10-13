"""Single Groq client shared by every agent (one model for all, per spec)."""
import json
import re
import threading
import time

from config import env

_client = None
_lock = threading.Lock()


def model_name() -> str:
    return env("GROQ_MODEL", "llama-3.3-70b-versatile")


def client():
    global _client
    with _lock:
        if _client is None:
            from groq import Groq
            _client = Groq(api_key=env("GROQ_API_KEY", required=True), max_retries=0)
        return _client


def _call(fn, attempts: int = 3):
    """Retry on rate limits / transient errors with backoff."""
    delay = 2.0
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # groq raises typed errors; match on text to stay version-proof
            text = str(exc).lower()
            transient = any(s in text for s in ("429", "rate limit", "timeout", "503", "502", "overloaded"))
            if i == attempts - 1 or not transient:
                raise
            time.sleep(delay)
            delay *= 2


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1800) -> str:
    res = _call(lambda: client().chat.completions.create(
        model=model_name(), messages=messages, temperature=temperature, max_tokens=max_tokens))
    return (res.choices[0].message.content or "").strip()


def _extract_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def chat_json(messages: list[dict], temperature: float = 0.1, max_tokens: int = 1500) -> dict:
    """Ask for a JSON object; returns {} if the model produced nothing parseable."""
    try:
        res = _call(lambda: client().chat.completions.create(
            model=model_name(), messages=messages, temperature=temperature,
            max_tokens=max_tokens, response_format={"type": "json_object"}))
        text = res.choices[0].message.content or ""
    except Exception:
        text = chat(messages, temperature=temperature, max_tokens=max_tokens)
    data = _extract_json(text)
    return data if isinstance(data, dict) else {}


def chat_tools(messages: list[dict], tools: list[dict], max_tokens: int = 1500) -> list[tuple[str, dict]]:
    """Function-calling. Returns [(tool_name, args_dict), ...]; [] on failure."""
    try:
        res = _call(lambda: client().chat.completions.create(
            model=model_name(), messages=messages, tools=tools, tool_choice="auto",
            temperature=0.0, max_tokens=max_tokens))
    except Exception:
        return []
    calls = []
    for tc in (res.choices[0].message.tool_calls or []):
        try:
            args = json.loads(tc.function.arguments or "{}")
        except Exception:
            args = {}
        calls.append((tc.function.name, args if isinstance(args, dict) else {}))
    return calls
