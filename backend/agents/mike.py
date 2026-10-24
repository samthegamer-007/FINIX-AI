"""Agent 6 — Mike: presenter. Picks fixed chart tools, renders static PNGs, uploads
them, and (on request) builds the PDF (fpdf2) / CSV exports. Mike never calculates."""
import json

import llm
import repo
from agents.common import frames_from_rome, trace, emit
from datetime import date

from config import DISCLAIMER, env
from tools import mike_tools as mt

SYSTEM = (
    "You are Mike, the presenter agent of FINIX. Decide which charts best communicate the analysis, using ONLY "
    "the provided tools and ONLY the series/tables listed as available (copy keys exactly). Max 4 charts, no "
    "duplicates. Guidance: single symbol with indicators -> candlestick_chart (overlay_key = indicators_<SYMBOL>) "
    "plus indicator_panel RSI_14; several symbols -> line_chart on cumulative_returns; portfolio -> pie_chart on "
    "table 'allocation' and line_chart on portfolio_cumulative; correlation -> heatmap_chart; risk -> line_chart "
    "on drawdown_<SYMBOL>. Give each chart a short descriptive title."
)


def _assets(state) -> mt.Assets:
    series = dict(state.get("kova_series") or {})
    for sym, df in frames_from_rome(state.get("rome") or {}).items():
        series[f"ohlc_{sym}"] = df
    return mt.Assets(series=series, tables=dict(state.get("kova_tables") or {}))


def _catalog(assets: mt.Assets) -> str:
    lines = ["Series:"]
    for k, df in assets.series.items():
        if k.startswith("ohlc_"):
            lines.append(f"- {k} (raw OHLC, use candlestick_chart with symbol={k[5:]})")
        else:
            lines.append(f"- {k}: columns {list(map(str, df.columns))[:8]}")
    lines.append("Tables:")
    lines += [f"- {k}" for k in assets.tables]
    return "\n".join(lines)


def _fallback(assets: mt.Assets):
    calls = []
    ohlc = [k[5:] for k in assets.series if k.startswith("ohlc_")]
    if ohlc:
        ov = f"indicators_{ohlc[0]}"
        calls.append(("candlestick_chart", {"symbol": ohlc[0], "overlay_key": ov if ov in assets.series else None,
                                             "title": f"{ohlc[0]} price"}))
    if "cumulative_returns" in assets.series:
        calls.append(("line_chart", {"series_key": "cumulative_returns", "columns": [], "title": "Cumulative returns"}))
    if "allocation" in assets.tables:
        calls.append(("pie_chart", {"table_key": "allocation", "title": "Portfolio allocation"}))
    if "correlation" in assets.series:
        calls.append(("heatmap_chart", {"series_key": "correlation", "title": "Return correlation"}))
    return calls


def _sig(name, args):
    return (name, args.get("symbol") or args.get("series_key") or args.get("table_key"), args.get("column"))


def _baseline(assets: mt.Assets):
    """Deterministic core charts so a 'with charts' request never yields just one picture."""
    calls = []
    ohlc = [k[5:] for k in assets.series if k.startswith("ohlc_")]
    sym = ohlc[0] if ohlc else None
    ind = f"indicators_{sym}" if sym else None
    if sym:
        calls.append(("candlestick_chart", {"symbol": sym, "overlay_key": ind if ind in assets.series else None,
                                             "title": f"{sym} price with indicators"}))
        if ind in assets.series and "RSI_14" in assets.series[ind].columns:
            calls.append(("indicator_panel", {"series_key": ind, "column": "RSI_14", "title": f"{sym} RSI (14)"}))
    cum = assets.series.get("cumulative_returns")
    if cum is not None and len(cum.columns) > 1:
        calls.append(("line_chart", {"series_key": "cumulative_returns", "columns": [], "title": "Cumulative returns"}))
    elif sym and f"drawdown_{sym}" in assets.series:
        calls.append(("line_chart", {"series_key": f"drawdown_{sym}", "columns": [], "title": f"{sym} drawdown"}))
    if "allocation" in assets.tables:
        calls.append(("pie_chart", {"table_key": "allocation", "title": "Portfolio allocation"}))
    if "correlation" in assets.series:
        calls.append(("heatmap_chart", {"series_key": "correlation", "title": "Return correlation"}))
    return calls


def charts(state, config):
    assets = _assets(state)
    out_charts, pngs, chart_errors = [], [], []
    if not assets.series and not assets.tables:
        return {"charts": [], "chart_pngs": [], "chart_errors": ["no data available to chart"],
                "done": state["done"] + ["mike_charts"]}

    trace(config, "Mike", "Deciding which visuals tell the story...")
    calls = llm.chat_tools(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": f"User asked: {state['user_text'][:300]}\n\n{_catalog(assets)}"}],
        mt.groq_tool_specs())
    calls = _baseline(assets) + list(calls) + _fallback(assets)

    uid, chat_id = state["user_id"], state["chat_id"]
    seen, planned = set(), []
    for name, args in calls:
        sig = _sig(name, args)
        if sig not in seen:
            seen.add(sig)
            planned.append((name, args))
    for name, args in planned[:4]:
        try:
            trace(config, "Mike", f"Rendering {name.replace('_', ' ')}...")
            res = mt.run_chart_tool(name, args, assets)
            url = repo.upload_bytes(env("CHARTS_BUCKET", "charts"), uid, res.png, "png", "image/png",
                                    name=mt.slugify(res.title, 40))
            seq = repo.next_chart_seq(chat_id)
            row = repo.add_chart(chat_id, uid, seq, res.title, res.kind, url, res.meta)
            item = {"tag": row["tag"], "seq": seq, "title": res.title, "kind": res.kind, "url": url}
            out_charts.append(item)
            pngs.append((f"{row['tag']}  {res.title}", res.png))
            emit(config, "chart", item)
            trace(config, "Mike", f"Created {row['tag']} - {res.title}")
        except Exception as exc:
            chart_errors.append(f"{name} failed to render")
            trace(config, "Mike", f"Skipped {name}: {str(exc)[:90]}")
    return {"charts": out_charts, "chart_pngs": pngs, "chart_errors": chart_errors,
            "done": state["done"] + ["mike_charts"]}


def _report_title(plan: dict) -> str:
    if plan.get("report_title"):
        return str(plan["report_title"])[:80]
    syms = " ".join((plan.get("symbols") or [])[:3])
    return f"{syms} analysis report".strip() if syms else "FINIX analysis report"


def export(state, config):
    plan, uid = state["plan"], state["user_id"]
    title = _report_title(plan)
    base = f"{mt.slugify(title, 50)}-{date.today().isoformat()}"
    files, note = [], ""
    text = state.get("final_text", "")
    bucket = env("EXPORTS_BUCKET", "exports")

    if plan.get("want_pdf"):
        trace(config, "Mike", "Assembling PDF report...")
        try:
            pdf = mt.generate_pdf(title, text, state.get("chart_pngs") or [], DISCLAIMER)
            url = repo.upload_bytes(bucket, uid, pdf, "pdf", "application/pdf", name=base)
            item = {"name": f"{base}.pdf", "kind": "pdf", "url": url}
            files.append(item)
            emit(config, "file", item)
            trace(config, "Mike", "PDF report ready.")
        except Exception as exc:
            note += f"\n\n_(PDF export failed: {str(exc)[:80]})_"
    if plan.get("want_csv"):
        trace(config, "Mike", "Writing CSV export...")
        try:
            assets = _assets(state)
            if not assets.series and not assets.tables:
                raise ValueError("no computed data to export")
            csv = mt.generate_csv(assets)
            url = repo.upload_bytes(bucket, uid, csv, "csv", "text/csv", name=f"{mt.slugify(title, 40)}-data-{date.today().isoformat()}")
            item = {"name": f"{mt.slugify(title, 40)}-data-{date.today().isoformat()}.csv", "kind": "csv", "url": url}
            files.append(item)
            emit(config, "file", item)
            trace(config, "Mike", "CSV export ready.")
        except Exception as exc:
            note += f"\n\n_(CSV export failed: {str(exc)[:80]})_"
    return {"files": files, "final_text": text + note, "done": state["done"] + ["mike_export"]}
