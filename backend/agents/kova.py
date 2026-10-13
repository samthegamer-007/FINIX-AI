"""Agent 3 — Kova: quantitative core. The LLM only SELECTS fixed tools (function
calling, Pydantic-validated args); all maths runs in tools/kova_tools.py."""
import json

import llm
from agents.common import PERIODS_PER_YEAR, compact, frames_from_rome, trace
from tools import kova_tools as kt

SYSTEM = (
    "You are Kova, the quantitative agent of FINIX. You never do arithmetic yourself: you call the provided "
    "tools. Choose the smallest useful set of tools (max 6 calls) for the analysis goal. Use only symbols "
    "listed as available. For one symbol typically call performance_summary, sharpe_ratio, max_drawdown and "
    "technical_indicators (rsi, macd, bbands, sma). For several symbols add correlation_matrix. If the user "
    "has declared holdings and the goal concerns the portfolio, call portfolio_risk."
)


def _defaults(symbols, intent, has_holdings):
    calls = [("performance_summary", {"symbols": symbols})]
    first = symbols[0]
    calls += [("sharpe_ratio", {"symbol": first}), ("max_drawdown", {"symbol": first}),
              ("technical_indicators", {"symbol": first, "indicators": ["rsi", "macd", "sma", "bbands"]})]
    if len(symbols) > 1:
        calls.append(("correlation_matrix", {"symbols": symbols}))
    if has_holdings and intent == "portfolio":
        calls.append(("portfolio_risk", {}))
    return calls


def run(state, config):
    plan, rome = state["plan"], state.get("rome") or {}
    frames = frames_from_rome(rome)
    holdings = state.get("holdings") or []
    if not frames:
        trace(config, "Kova", "No price data available - skipping calculations.")
        return {"kova_results": [], "kova_series": {}, "kova_tables": {}, "kova_errors": ["no price data"],
                "done": state["done"] + ["kova"]}

    symbols = list(frames)
    ctx = kt.Ctx(frames=frames, holdings=holdings, periods=PERIODS_PER_YEAR.get(plan["interval"], 252))
    trace(config, "Kova", f"Choosing calculations for {', '.join(symbols)}...")

    user_msg = (f"Analysis goal: {plan.get('analysis_goal') or state['user_text'][:300]}\n"
                f"Intent: {plan['intent']}\nAvailable symbols: {symbols}\n"
                f"Declared holdings priced: {[h['symbol'] for h in holdings if h['symbol'].upper() in frames]}")
    calls = llm.chat_tools([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg}],
                           kt.groq_tool_specs())
    if not calls:
        trace(config, "Kova", "Using the standard analysis set.")
        calls = _defaults(symbols, plan["intent"], bool(holdings))
    elif plan["intent"] == "portfolio" and holdings and not any(n == "portfolio_risk" for n, _ in calls):
        calls.append(("portfolio_risk", {}))

    results, series, tables, errors, seen = [], {}, {}, [], set()
    for name, args in calls[:8]:
        key = name + json.dumps(args, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        trace(config, "Kova", f"Running {name}{'(' + str(args.get('symbol') or ','.join(args.get('symbols', []))) + ')' if args else ''}...")
        try:
            res = kt.run_tool(name, args, ctx)
            results.append({"tool": name, "args": args, "result": res.summary})
            series.update(res.series)
            tables.update(res.tables)
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:140]}")
            trace(config, "Kova", f"{name} failed: {str(exc)[:80]}")

    trace(config, "Kova", f"Done - {len(results)} calculation(s), {len(series)} series ready for Mike.")
    return {"kova_results": results, "kova_series": series, "kova_tables": tables, "kova_errors": errors,
            "done": state["done"] + ["kova"]}
