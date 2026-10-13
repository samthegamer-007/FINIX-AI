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
    "\"portfolio_adjustments\": [\"max 3 concrete actions, or empty\"]}"
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
