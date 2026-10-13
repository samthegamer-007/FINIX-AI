"""Agent 6 — Mike: presenter. Picks fixed chart tools, renders static PNGs, uploads
them, and (on request) builds the PDF (fpdf2) / CSV exports. Mike never calculates."""
import json

import llm
import repo
from agents.common import frames_from_rome, trace, emit
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


def charts(state, config):
    assets = _assets(state)
    out_charts, pngs = [], []
    if not assets.series and not assets.tables:
        return {"charts": [], "chart_pngs": [], "done": state["done"] + ["mike_charts"]}

    trace(config, "Mike", "Deciding which visuals tell the story...")
    calls = llm.chat_tools(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": f"User asked: {state['user_text'][:300]}\n\n{_catalog(assets)}"}],
        mt.groq_tool_specs())
    if not calls:
        calls = _fallback(assets)

    uid, chat_id = state["user_id"], state["chat_id"]
    seen = set()
    for name, args in calls[:4]:
        key = name + json.dumps(args, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        try:
            trace(config, "Mike", f"Rendering {name.replace('_', ' ')}...")
            res = mt.run_chart_tool(name, args, assets)
            url = repo.upload_bytes(env("CHARTS_BUCKET", "charts"), uid, res.png, "png", "image/png")
            seq = repo.next_chart_seq(chat_id)
            row = repo.add_chart(chat_id, uid, seq, res.title, res.kind, url, res.meta)
            item = {"tag": row["tag"], "seq": seq, "title": res.title, "kind": res.kind, "url": url}
            out_charts.append(item)
            pngs.append((f"{row['tag']}  {res.title}", res.png))
            emit(config, "chart", item)
            trace(config, "Mike", f"Created {row['tag']} - {res.title}")
        except Exception as exc:
            trace(config, "Mike", f"Skipped {name}: {str(exc)[:90]}")
    return {"charts": out_charts, "chart_pngs": pngs, "done": state["done"] + ["mike_charts"]}


def export(state, config):
    plan, uid = state["plan"], state["user_id"]
    files, note = [], ""
    text = state.get("final_text", "")
    bucket = env("EXPORTS_BUCKET", "exports")

    if plan.get("want_pdf"):
        trace(config, "Mike", "Assembling PDF report...")
        try:
            title = plan.get("report_title") or "FINIX analysis report"
            pdf = mt.generate_pdf(title, text, state.get("chart_pngs") or [], DISCLAIMER)
            url = repo.upload_bytes(bucket, uid, pdf, "pdf", "application/pdf")
            item = {"name": "finix-report.pdf", "kind": "pdf", "url": url}
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
            url = repo.upload_bytes(bucket, uid, csv, "csv", "text/csv")
            item = {"name": "finix-data.csv", "kind": "csv", "url": url}
            files.append(item)
            emit(config, "file", item)
            trace(config, "Mike", "CSV export ready.")
        except Exception as exc:
            note += f"\n\n_(CSV export failed: {str(exc)[:80]})_"
    return {"files": files, "final_text": text + note, "done": state["done"] + ["mike_export"]}
