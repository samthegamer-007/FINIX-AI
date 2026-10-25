"""Rome's data fetchers. STRICT RULE: no calculations, no transformations of values.
Everything returned is raw payload exactly as the source provided it."""
from datetime import datetime, timedelta, timezone

import requests

from config import env

HTTP_TIMEOUT = 15


def fetch_price_history(symbol: str, period: str = "1y", interval: str = "1d", lookback_days: int | None = None) -> dict:
    import yfinance as yf
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        return {"symbol": symbol, "error": "no data returned", "records": []}
    if lookback_days:                      # keep only the requested trailing window (row selection, no maths)
        import pandas as pd
        df = df[df.index >= df.index.max() - pd.Timedelta(days=int(lookback_days))]
    df = df.reset_index()
    date_col = df.columns[0]
    df[date_col] = df[date_col].astype(str)
    df = df.rename(columns={date_col: "Date"})
    keep = [c for c in ("Date", "Open", "High", "Low", "Close", "Volume") if c in df.columns]
    return {"symbol": symbol, "period": period, "interval": interval, "records": df[keep].to_dict("records")}


def fetch_fundamentals(symbol: str) -> dict:
    import yfinance as yf
    t = yf.Ticker(symbol)
    out = {"symbol": symbol}
    try:
        info = t.info or {}
        keys = ("longName", "sector", "industry", "marketCap", "trailingPE", "forwardPE", "priceToBook",
                "dividendYield", "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currency", "totalRevenue",
                "profitMargins", "returnOnEquity", "debtToEquity")
        out["info"] = {k: info.get(k) for k in keys if k in info}
    except Exception as exc:
        out["info_error"] = str(exc)[:120]
    try:
        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            col = bs.columns[0]
            out["balance_sheet_date"] = str(col)
            out["balance_sheet"] = {str(k): (None if v != v else float(v)) for k, v in bs[col].items()}
    except Exception as exc:
        out["balance_sheet_error"] = str(exc)[:120]
    return out


def fetch_news(query: str, limit: int = 8) -> dict:
    key = env("NEWSAPI_KEY")
    if not key:
        return {"query": query, "articles": [], "error": "NEWSAPI_KEY not set"}
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "from": since, "language": "en", "sortBy": "publishedAt", "pageSize": limit},
            headers={"X-Api-Key": key}, timeout=HTTP_TIMEOUT)
        data = r.json()
    except Exception as exc:
        return {"query": query, "articles": [], "error": str(exc)[:120]}
    if data.get("status") != "ok":
        return {"query": query, "articles": [], "error": data.get("message", "NewsAPI error")}
    arts = [{"title": a.get("title"), "source": (a.get("source") or {}).get("name"),
             "published": a.get("publishedAt"), "description": a.get("description"), "url": a.get("url")}
            for a in data.get("articles", [])]
    return {"query": query, "articles": arts}


def fetch_web(query: str, limit: int = 5) -> dict:
    key = env("TAVILY_API_KEY")
    if not key:
        return {"query": query, "results": [], "error": "TAVILY_API_KEY not set"}
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {key}"},
            json={"query": query, "max_results": limit, "search_depth": "basic", "include_answer": True},
            timeout=HTTP_TIMEOUT)
        data = r.json()
    except Exception as exc:
        return {"query": query, "results": [], "error": str(exc)[:120]}
    return {"query": query, "answer": data.get("answer"),
            "results": [{"title": x.get("title"), "url": x.get("url"), "content": (x.get("content") or "")[:600]}
                        for x in data.get("results", [])]}
