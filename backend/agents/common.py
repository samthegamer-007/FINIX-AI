import json
from datetime import date

import pandas as pd


def emit(config, kind: str, data: dict):
    fn = (config or {}).get("configurable", {}).get("emit")
    if fn:
        try:
            fn(kind, data)
        except Exception:
            pass


def trace(config, agent: str, msg: str):
    emit(config, "trace", {"agent": agent, "msg": msg})


def compact(obj, limit: int = 3500) -> str:
    """JSON-dump for prompts, hard-capped so we stay inside Groq token limits."""
    s = json.dumps(obj, default=str, separators=(",", ":"))
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


def today() -> str:
    return date.today().isoformat()


PERIODS_PER_YEAR = {"1d": 252, "1wk": 52, "1mo": 12}


def frames_from_rome(rome: dict) -> dict[str, pd.DataFrame]:
    """Rebuild date-indexed OHLCV frames from Rome's raw records (pure re-shaping, no maths)."""
    out = {}
    for sym, payload in (rome.get("prices") or {}).items():
        recs = payload.get("records") or []
        if not recs:
            continue
        df = pd.DataFrame(recs)
        idx = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_convert(None)
        df = df.drop(columns=["Date"]).set_index(idx)
        df = df[~df.index.isna()].sort_index()
        for c in ("Open", "High", "Low", "Close", "Volume"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        out[sym.upper()] = df.dropna(subset=["Close"])
    return out
