"""Agent 4 — Dimon: decision taker. Synthesises Kova's numbers with Rome's news context."""
import llm
from agents.common import compact, trace

SYSTEM = (
    "You are Dimon, the decision engine of FINIX AI: a decisive senior portfolio strategist. You are given "
    "QUANT RESULTS (from Kova), NEWS/WEB context (from Rome), the user's declared holdings and memory. "
    "Produce a definitive recommendation. Rules: use ONLY numbers present in the quant results - never "
    "invent or recompute figures; if evidence is thin, say so and lower confidence; weigh numbers against "
    "news sentiment; always include concrete risks. Return JSON: "
    "{\"stance\": \"buy|add|hold|reduce|sell|avoid|rebalance|neutral\", \"headline\": \"one-line verdict\", "
    "\"confidence\": \"low|medium|high\", \"time_horizon\": \"short text\", "
    "\"rationale\": [\"max 4 bullets citing the numbers\"], \"risks\": [\"max 3 bullets\"], "
    "\"portfolio_adjustments\": [\"max 3 concrete actions, or empty\"]}. "
    "portfolio_adjustments: ONLY if the user's declared holdings are provided and relevant; if holdings is empty "
    "return [] and never assume the user already owns the security. Do not suggest other securities, ETFs or "
    "sectors unless the supplied data supports it."
)


def run(state, config):
    trace(config, "Dimon", "Weighing quantitative results against the news landscape...")
    rome = state.get("rome") or {}
    news = [{"t": a.get("title"), "s": a.get("source"), "d": (a.get("description") or "")[:160]}
            for a in ((rome.get("news") or {}).get("articles") or [])[:6]]
    web = (rome.get("web") or {})
    ctx = {
        "question": state["user_text"][:500],
        "intent": state["plan"]["intent"],
        "quant": state.get("kova_results") or [],
        "fundamentals": rome.get("fundamentals") or {},
        "news": news,
        "web_answer": (web.get("answer") or "")[:500],
        "holdings": [{k: h.get(k) for k in ("symbol", "quantity", "avg_price")} for h in (state.get("holdings") or [])][:15],
        "memory": state.get("memory_ctx", "")[:800],
        "data_gaps": (rome.get("errors") or []) + (state.get("kova_errors") or []),
    }
    decision = llm.chat_json([{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": compact(ctx, 6000)}], max_tokens=900)
    if not decision.get("stance"):
        decision = {"stance": "neutral", "headline": "Insufficient evidence for a firm call.",
                    "confidence": "low", "rationale": [], "risks": ["Decision engine returned no structured output."],
                    "portfolio_adjustments": [], "time_horizon": "n/a"}
    trace(config, "Dimon", f"Verdict: {decision.get('stance')} ({decision.get('confidence')} confidence).")
    return {"dimon": decision, "done": state["done"] + ["dimon"]}


# ------------------------------------------------------------------ qualitative outlook
OUTLOOK_SYSTEM = (
    "You are Dimon, producing the QUALITATIVE OUTLOOK for FINIX AI. Inputs: numbered SOURCES (news and web results), "
    "SENTIMENT (a lexicon score computed in code), SIMULATION (quant percentile ranges) and fundamentals. "
    "Rules: use ONLY the numbered sources; every driver and precedent must cite a source number in \"src\". "
    "Precedents are past episodes or analogues described in the sources; if the sources contain none, return an "
    "empty list. Never invent events, dates, numbers or causes. Be balanced, and say what would change the view. "
    "Return JSON: {\"sentiment_read\": \"1-2 sentences\", "
    "\"drivers_up\": [{\"point\": \"...\", \"src\": 1}], \"drivers_down\": [{\"point\": \"...\", \"src\": 2}], "
    "\"precedents\": [{\"episode\": \"...\", \"what_happened\": \"...\", \"src\": 3}], "
    "\"scenarios\": {\"bull\": {\"story\": \"...\", \"trigger\": \"...\"}, \"base\": {...}, \"bear\": {...}}, "
    "\"watch_list\": [\"dated catalysts or indicators, only if in the sources\"], "
    "\"confidence\": \"low|medium|high\", \"caveats\": [\"max 3\"]}. Max 4 items per list."
)


def _collect_sources(rome: dict) -> list[dict]:
    srcs = []
    for a in ((rome.get("news") or {}).get("articles") or [])[:8]:
        if a.get("title"):
            srcs.append({"kind": "news", "title": a["title"], "url": a.get("url"), "text": (a.get("description") or "")[:240],
                         "outlet": a.get("source")})
    for key, kind in (("web", "web"), ("precedents", "precedent")):
        blob = rome.get(key) or {}
        for r in (blob.get("results") or [])[:5]:
            if r.get("title"):
                srcs.append({"kind": kind, "title": r["title"], "url": r.get("url"), "text": (r.get("content") or "")[:420]})
        if blob.get("answer") and key == "web":
            srcs.append({"kind": "web", "title": "Web summary", "url": None, "text": str(blob["answer"])[:420]})
    return srcs


def _clean_items(items, n_src, need_src=True):
    out = []
    for it in (items or [])[:4]:
        if not isinstance(it, dict):
            continue
        try:
            src = int(it.get("src"))
        except (TypeError, ValueError):
            src = None
        if src is not None and not (1 <= src <= n_src):
            src = None
        if need_src and src is None:
            continue                                    # unsourced precedents/drivers are dropped, never kept
        out.append({**{k: str(v)[:260] for k, v in it.items() if k != "src"}, "src": src})
    return out


def outlook(state, config):
    trace(config, "Dimon", "Building the qualitative outlook from news, sentiment and precedents...")
    rome = state.get("rome") or {}
    srcs = _collect_sources(rome)
    sentiment = next((r["result"] for r in (state.get("kova_results") or []) if r["tool"] == "news_sentiment"), None)
    sims = [{k: r["result"].get(k) for k in ("symbol", "model", "horizon_trading_days", "return_p5", "return_p50", "return_p95",
                                              "probability_of_loss", "forecast_annual_vol")}
            for r in (state.get("kova_results") or []) if r["tool"] == "price_simulation"]
    if not srcs:
        trace(config, "Dimon", "No news or web sources available - outlook limited to the numbers.")
        return {"outlook": {"sources": [], "confidence": "low", "caveats": ["No news or web sources were available, so there is no qualitative outlook."]},
                "done": state["done"] + ["outlook"]}
    ctx = {
        "question": state["user_text"][:400],
        "symbols": (state.get("plan") or {}).get("symbols"),
        "SOURCES": [{"n": i + 1, "kind": s["kind"], "title": s["title"], "text": s["text"]} for i, s in enumerate(srcs)],
        "SENTIMENT": sentiment,
        "SIMULATION": sims[:4],
        "fundamentals": rome.get("fundamentals") or {},
        "memory": state.get("memory_ctx", "")[:500],
    }
    raw = llm.chat_json([{"role": "system", "content": OUTLOOK_SYSTEM}, {"role": "user", "content": compact(ctx, 7000)}],
                        max_tokens=1100)
    n = len(srcs)
    scen = raw.get("scenarios") if isinstance(raw.get("scenarios"), dict) else {}
    result = {
        "sentiment_read": str(raw.get("sentiment_read") or "")[:300],
        "drivers_up": _clean_items(raw.get("drivers_up"), n),
        "drivers_down": _clean_items(raw.get("drivers_down"), n),
        "precedents": _clean_items(raw.get("precedents"), n),
        "scenarios": {k: {kk: str(vv)[:260] for kk, vv in (scen.get(k) or {}).items()} for k in ("bull", "base", "bear") if isinstance(scen.get(k), dict)},
        "watch_list": [str(x)[:160] for x in (raw.get("watch_list") or [])[:4]],
        "confidence": raw.get("confidence") if raw.get("confidence") in ("low", "medium", "high") else "low",
        "caveats": [str(x)[:200] for x in (raw.get("caveats") or [])[:3]],
    }
    cited = sorted({it["src"] for k in ("drivers_up", "drivers_down", "precedents") for it in result[k] if it.get("src")})
    result["sources"] = [{"n": i, "title": srcs[i - 1]["title"], "url": srcs[i - 1]["url"]} for i in cited]
    for k in ("drivers_up", "drivers_down", "precedents"):          # expose the source title, not just a number
        for it in result[k]:
            if it.get("src"):
                it["source"] = srcs[it["src"] - 1]["title"][:90]
    trace(config, "Dimon", f"Outlook ready: {len(result['drivers_up'])} up / {len(result['drivers_down'])} down drivers, "
                           f"{len(result['precedents'])} sourced precedent(s), confidence {result['confidence']}.")
    return {"outlook": result, "done": state["done"] + ["outlook"]}
