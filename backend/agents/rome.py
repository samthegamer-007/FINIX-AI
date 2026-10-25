"""Agent 2 — Rome: raw data ingestion. Zero calculations. Output is untouched source payloads."""
from concurrent.futures import ThreadPoolExecutor

from agents.common import trace
from tools import rome_tools as rt


def run(state, config):
    plan = state["plan"]
    symbols = plan.get("symbols") or []
    out = {"prices": {}, "fundamentals": {}, "news": None, "web": None, "errors": []}

    def prices(sym):
        span = f"last {plan['lookback_days']} days" if plan.get("lookback_days") else plan["period"]
        trace(config, "Rome", f"Fetching {span} price history for {sym}...")
        try:
            return sym, rt.fetch_price_history(sym, plan["period"], plan["interval"], plan.get("lookback_days"))
        except Exception as exc:
            return sym, {"symbol": sym, "error": str(exc)[:120], "records": []}

    if symbols:
        with ThreadPoolExecutor(max_workers=min(5, len(symbols))) as pool:
            for sym, payload in pool.map(prices, symbols):
                if payload.get("records"):
                    out["prices"][sym] = payload
                else:
                    out["errors"].append(f"{sym}: {payload.get('error', 'no data')}")

    if plan.get("need_fundamentals") and symbols:
        for sym in symbols[:3]:
            trace(config, "Rome", f"Pulling fundamentals for {sym}...")
            try:
                out["fundamentals"][sym] = rt.fetch_fundamentals(sym)
            except Exception as exc:
                out["errors"].append(f"{sym} fundamentals: {str(exc)[:80]}")

    if plan.get("need_news"):
        q = plan.get("news_query") or " OR ".join(symbols[:3]) or "stock market"
        trace(config, "Rome", f"Scanning news for \"{q[:60]}\"...")
        out["news"] = rt.fetch_news(q)
        if out["news"].get("error"):
            out["errors"].append(f"news: {out['news']['error']}")

    if plan.get("web_query"):
        trace(config, "Rome", f"Searching the web: \"{plan['web_query'][:60]}\"...")
        out["web"] = rt.fetch_web(plan["web_query"])
        if out["web"].get("error"):
            out["errors"].append(f"web: {out['web']['error']}")

    got = ", ".join(out["prices"]) or "no prices"
    trace(config, "Rome", f"Data ready ({got}). Handing raw payload back to Finix.")
    return {"rome": out, "done": state["done"] + ["rome"]}
