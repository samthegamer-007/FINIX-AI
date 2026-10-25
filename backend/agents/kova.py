"""Agent 3 — Kova: quantitative core. The LLM only SELECTS fixed tools (function
calling, Pydantic-validated args); all maths runs in tools/kova_tools.py."""
import json

import llm
from agents.common import emit
from agents.common import PERIODS_PER_YEAR, compact, frames_from_rome, trace
from tools import kova_tools as kt

SYSTEM = (
    "You are Kova, the quantitative agent of FINIX. You never do arithmetic yourself: you call the provided "
    "tools. Choose the smallest useful set of tools (max 8 calls) for the analysis goal. Use only symbols "
    "listed as available. For one symbol typically call performance_summary, sharpe_ratio, max_drawdown and "
    "technical_indicators (rsi, macd, bbands, sma); return_distribution and monthly_returns feed the histogram and heatmap. For several symbols add correlation_matrix. If the user "
    "has declared holdings and the goal concerns the portfolio, call portfolio_risk."
)


def _defaults(symbols, intent, has_holdings, rows=999):
    """rows = number of price rows for the first symbol; skip tools that need more history than we have."""
    calls = [("performance_summary", {"symbols": symbols})]
    first = symbols[0]
    calls += [("sharpe_ratio", {"symbol": first}), ("max_drawdown", {"symbol": first}),
              ("return_distribution", {"symbol": first})]
    if rows >= 70:
        calls.append(("monthly_returns", {"symbol": first}))
    inds = [i for i, need in (("rsi", 16), ("macd", 36), ("sma", 21), ("bbands", 21)) if rows >= need]
    if inds:
        calls.append(("technical_indicators", {"symbol": first, "indicators": inds}))
    if len(symbols) > 1:
        calls.append(("correlation_matrix", {"symbols": symbols}))
    if has_holdings and intent == "portfolio":
        calls.append(("portfolio_risk", {}))
    return calls


NOTES = {
    "performance_summary": "r_t = P_t/P_(t-1) - 1; total = prod(1+r) - 1; CAGR; annualised vol = std(r)*sqrt(N)",
    "sharpe_ratio": "Sharpe = (mean(r) - rf) / std(r) * sqrt(N)",
    "sortino_ratio": "Sortino = (mean(r) - rf) / downside_std(r) * sqrt(N)",
    "max_drawdown": "DD_t = NAV_t / max(NAV_0..t) - 1; max drawdown = min(DD)",
    "value_at_risk": "VaR = percentile of period returns at the chosen confidence",
    "technical_indicators": "RSI(14), MACD(12,26,9), Bollinger(20,2), SMA(20/50) via pandas-ta",
    "return_distribution": "mean, std, skew, excess kurtosis, share of positive periods",
    "monthly_returns": "month-end close to month-end close, grouped by year x month",
    "correlation_matrix": "Pearson correlation of aligned period returns",
    "portfolio_risk": "weights = qty x last price / total; portfolio r = sum(w x r_i)",
}


def _rows(obj, prefix=""):
    """Flatten a (nested) summary dict into [label, value] rows for the calculation console."""
    rows = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            rows += _rows(v, f"{prefix}{k}.")
    else:
        rows.append([prefix.rstrip("."), obj])
    return rows


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
    # The baseline set always runs (deterministic); the LLM's choices are added on top of it.
    calls = _defaults(symbols, plan["intent"], bool(holdings), len(frames[symbols[0]])) + list(calls)

    results, series, tables, errors, seen = [], {}, {}, [], set()
    for name, args in calls[:12]:
        key = name + json.dumps(args, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        trace(config, "Kova", f"Running {name}{'(' + str(args.get('symbol') or ','.join(args.get('symbols', []))) + ')' if args else ''}...")
        try:
            res = kt.run_tool(name, args, ctx)
            results.append({"tool": name, "args": args, "result": res.summary})
            emit(config, "calc", {"tool": name, "args": args, "note": NOTES.get(name, ""),
                                  "rows": _rows(res.summary)[:24]})
            for k, df in res.series.items():
                if k in series and k.startswith("indicators_"):      # merge indicator sets for the same symbol
                    extra = df.loc[:, ~df.columns.isin(series[k].columns)]
                    series[k] = series[k].join(extra)
                else:
                    series[k] = df
            tables.update(res.tables)
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:140]}")
            trace(config, "Kova", f"{name} failed: {str(exc)[:80]}")

    trace(config, "Kova", f"Done - {len(results)} calculation(s), {len(series)} series ready for Mike.")
    return {"kova_results": results, "kova_series": series, "kova_tables": tables, "kova_errors": errors,
            "done": state["done"] + ["kova"]}
