"""Agent 1 — Finix: orchestrator. Plans the request, routes to the spokes via the
LangGraph router, and composes the final answer. The user only ever talks to Finix."""
import re

import llm
from agents.common import compact, today, trace
from config import ALLOWED_INTERVALS, ALLOWED_PERIODS, DISCLAIMER, MAX_SYMBOLS

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")

PERIOD_WORDS = {"1mo": "last 1 month", "3mo": "last 3 months", "6mo": "last 6 months", "1y": "last 12 months",
                "2y": "last 2 years", "5y": "last 5 years", "ytd": "year to date", "max": "full available history"}
LABELS = {"mike_charts": "mike (charts)", "mike_export": "mike (files)"}

PLAN_SYSTEM = """You are Finix, orchestrator of a multi-agent financial intelligence system. Today is {today}.
Read the user's message (plus declared holdings, memory, referenced charts, attachments) and return ONE JSON object:
{{
 "intent": "chitchat" | "research" | "decision" | "portfolio",
 "symbols": [up to 5 Yahoo Finance tickers; NSE stocks end in .NS, BSE in .BO, indices like ^NSEI, crypto like BTC-USD],
 "period": "1mo|3mo|6mo|1y|2y|5y|ytd|max",
 "interval": "1d|1wk|1mo",
 "need_news": true/false,
 "news_query": "short NewsAPI query or null",
 "web_query": "short web search query or null (use for general market/macro/company questions needing fresh info)",
 "need_fundamentals": true/false,
 "analysis_goal": "one sentence for the quant agent",
 "need_decision": true/false,
 "want_charts": true/false,
 "want_pdf": true only if the user EXPLICITLY asks for a PDF/report file,
 "want_csv": true only if the user EXPLICITLY asks for a CSV/spreadsheet export,
 "report_title": "short descriptive document title such as 'AAPL Hold Recommendation' when want_pdf or want_csv, else null"
}}
Guidance: "chitchat" = greetings, how-it-works questions, anything needing no market data (symbols=[]). "decision" = buy/sell/hold/rebalance/should-I questions. "portfolio" = analyse the user's declared holdings (leave symbols empty; they are filled in from holdings). "research" = facts, trends, comparisons. Default period 1y, interval 1d. want_charts true whenever trends/numbers are involved unless the user declines charts. If the message refers to a chart like #Graph-04, use that chart's metadata to infer symbols/series. Return JSON only."""

COMPOSE_SYSTEM = """You are Finix, the lead analyst of FINIX AI, replying to the user. Voice: a sharp senior analyst - direct, specific, no filler, no hedging boilerplate, no lectures. Use light markdown (short paragraphs, bullets only when scanning helps, bold for key numbers).
Hard rules:
- Use ONLY figures present in the provided QUANT RESULTS / DATA. Never invent or recompute numbers. If something is missing or a data fetch failed, say so plainly.
- If a DECISION is provided, lead with its verdict, then the evidence (numbers), then risks and any portfolio adjustments.
- Refer to charts by their exact tags (e.g. #Graph-03) when pointing at them; never mention a tag that is not in CHARTS.
- Do NOT compare to "the market", an index, peers or any benchmark unless that comparison is explicitly in the data. Do NOT give price targets, stop-losses, entry/exit levels or trade advice unless a DECISION is provided; for plain research just report and interpret the numbers.
- Use PERIOD_ANALYSED exactly for the time window (e.g. "last 12 months"); never call it YTD unless it says year-to-date. Never mention internal field names such as data_frequency.
- RSI is a 0-100 index, never a percentage. Describe a chart only by its title and kind; do not claim it shows indicators its title does not name.
- No sign-offs, signatures or "Prepared by" lines. Do not add an "Attachments" section or list file names; the interface shows files and charts itself.
- Quant results labelled with data_frequency (day/week/month) describe single periods of that length; say "day", "week" or "month" accordingly, never a different period.
- If DATA_GAPS says charts failed or no data was available, say briefly that the charts could not be generated this time. Never ask the user to supply files or chart assets.
- If the user asked for a PDF/CSV, say it is attached below this message (do not paste the file contents).
- For casual/how-it-works questions just answer naturally and briefly; you may explain that Finix coordinates Rome (data), Kova (quant), Dimon (decisions), Frank (memory) and Mike (visuals).
- Do not add a disclaimer yourself; the system appends it."""


def _clean_plan(raw: dict, holdings: list[dict]) -> dict:
    intent = raw.get("intent") if raw.get("intent") in ("chitchat", "research", "decision", "portfolio") else "research"
    syms = []
    for s in raw.get("symbols") or []:
        s = str(s).upper().strip()
        if SYMBOL_RE.match(s) and s not in syms:
            syms.append(s)
    if intent == "portfolio" and not syms:
        syms = [str(h["symbol"]).upper() for h in sorted(holdings, key=lambda h: -(h.get("quantity") or 0))]
    plan = {
        "intent": intent,
        "symbols": syms[:MAX_SYMBOLS],
        "period": raw.get("period") if raw.get("period") in ALLOWED_PERIODS else "1y",
        "interval": raw.get("interval") if raw.get("interval") in ALLOWED_INTERVALS else "1d",
        "need_news": bool(raw.get("need_news")),
        "news_query": raw.get("news_query") or None,
        "web_query": raw.get("web_query") or None,
        "need_fundamentals": bool(raw.get("need_fundamentals")),
        "analysis_goal": str(raw.get("analysis_goal") or "")[:300],
        "need_decision": bool(raw.get("need_decision")) or intent == "decision",
        "want_charts": raw.get("want_charts", True) is not False,
        "want_pdf": bool(raw.get("want_pdf")),
        "want_csv": bool(raw.get("want_csv")),
        "report_title": raw.get("report_title") or None,
    }
    if intent == "chitchat" and not plan["symbols"]:
        plan.update(need_news=False, need_fundamentals=False, need_decision=False, want_charts=False)
    return plan


def derive_steps(plan: dict) -> list[str]:
    steps = []
    has_syms = bool(plan["symbols"])
    if has_syms or plan["need_news"] or plan["web_query"]:
        steps.append("rome")
    if has_syms:
        steps.append("kova")
    if plan["need_decision"] and (has_syms or plan["need_news"] or plan["web_query"]):
        steps.append("dimon")
    if plan["want_charts"] and has_syms:
        steps.append("mike_charts")
    steps.append("compose")
    if plan["want_pdf"] or plan["want_csv"]:
        steps.append("mike_export")
    return steps


def plan_node(state, config):
    trace(config, "Finix", "Reading your request and planning the work...")
    holdings = state.get("holdings") or []
    ctx = {
        "message": state["user_text"][:1500],
        "recent_chat": [{"r": m["role"], "c": m["content"][:300]} for m in (state.get("history") or [])[-4:]],
        "declared_holdings": [{k: h.get(k) for k in ("symbol", "quantity")} for h in holdings][:20],
        "memory": state.get("memory_ctx", "")[:800],
        "referenced_charts": [{"tag": c["tag"], "title": c["title"], "meta": c.get("meta")} for c in (state.get("ref_charts") or [])],
        "attachments": [{"file": a["filename"], "text": a["content_text"][:1500]} for a in (state.get("attachments") or [])],
    }
    raw = llm.chat_json([{"role": "system", "content": PLAN_SYSTEM.format(today=today())},
                         {"role": "user", "content": compact(ctx, 5000)}], max_tokens=700)
    plan = _clean_plan(raw, holdings)
    steps = derive_steps(plan)
    trace(config, "Finix", f"Plan: {plan['intent']}"
          + (f" on {', '.join(plan['symbols'])}" if plan["symbols"] else "")
          + f" -> {' > '.join(LABELS.get(s, s) for s in steps if s != 'compose') or 'direct reply'}")
    return {"plan": plan, "steps": steps, "done": []}


def router_node(state, config):
    """The hub. Every spoke returns here; Finix decides who is next."""
    for s in state["steps"]:
        if s not in state["done"]:
            if s != "compose":
                trace(config, "Finix", f"Delegating to {s.split('_')[0].capitalize()}...")
            return {"next": s}
    return {"next": "frank_store"}


def compose_node(state, config):
    trace(config, "Finix", "Composing the answer...")
    rome = state.get("rome") or {}
    news = [{"title": a.get("title"), "source": a.get("source")} for a in ((rome.get("news") or {}).get("articles") or [])[:5]]
    data = {
        "QUANT RESULTS": state.get("kova_results") or [],
        "DECISION": state.get("dimon"),
        "NEWS": news,
        "WEB": (rome.get("web") or {}).get("answer"),
        "FUNDAMENTALS": rome.get("fundamentals") or None,
        "PERIOD_ANALYSED": PERIOD_WORDS.get(state["plan"]["period"], state["plan"]["period"]),
        "CHARTS": [{"tag": c["tag"], "title": c["title"], "kind": c["kind"]} for c in (state.get("charts") or [])],
        "DATA_GAPS": (rome.get("errors") or []) + (state.get("kova_errors") or []) + (state.get("chart_errors") or []),
        "EXPORTS_REQUESTED": [k for k in ("pdf", "csv") if state["plan"].get(f"want_{k}")],
        "MEMORY": state.get("memory_ctx", "")[:800],
        "DECLARED_HOLDINGS": [{k: h.get(k) for k in ("symbol", "quantity", "avg_price")} for h in (state.get("holdings") or [])][:15],
        "ATTACHMENTS": [{"file": a["filename"], "text": a["content_text"][:3000]} for a in (state.get("attachments") or [])],
    }
    data = {k: v for k, v in data.items() if v not in (None, [], {}, "")}
    messages = [{"role": "system", "content": COMPOSE_SYSTEM}]
    for m in (state.get("history") or [])[-4:]:
        messages.append({"role": m["role"], "content": m["content"][:600]})
    messages.append({"role": "user", "content": f"{state['user_text'][:2000]}\n\n--- DATA FROM YOUR AGENTS ---\n{compact(data, 8000)}"})
    text = llm.chat(messages, temperature=0.35, max_tokens=1500)
    if not text:
        text = "I couldn't produce an answer this time. Please try again."
    if state.get("dimon"):
        text = f"{text.rstrip()}\n\n_{DISCLAIMER}_"
    return {"final_text": text, "done": state["done"] + ["compose"]}
