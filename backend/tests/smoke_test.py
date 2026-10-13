"""Offline smoke test: runs the full LangGraph with the LLM, Supabase and market data mocked,
while Kova (quantstats/pandas-ta) and Mike (matplotlib/mplfinance/fpdf2) run for real.
Run from backend/:  python -I tests/smoke_test.py   (needs no API keys)"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(SECRET_KEY="x", GROQ_API_KEY="x")
import numpy as np, pandas as pd

import llm, repo
from tools import rome_tools, kova_tools, mike_tools

def fake_prices(symbol, period="1y", interval="1d"):
    rng = np.random.default_rng(abs(hash(symbol)) % 2**32)
    idx = pd.bdate_range("2024-01-01", periods=300)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, 300)))
    df = pd.DataFrame({"Open": c*0.995, "High": c*1.01, "Low": c*0.99, "Close": c, "Volume": 1e6}, index=idx)
    df.index.name = "Date"
    df = df.reset_index(); df["Date"] = df["Date"].astype(str)
    return {"symbol": symbol, "records": df.to_dict("records")}
rome_tools.fetch_price_history = fake_prices
rome_tools.fetch_news = lambda q, limit=8: {"query": q, "articles": [{"title": "AAPL beats estimates", "source": "Wire", "description": "Strong quarter."}]}
rome_tools.fetch_web = lambda q, limit=5: {"query": q, "results": [], "answer": "Macro steady."}

PLAN = {"intent": "decision", "symbols": ["AAPL", "MSFT"], "period": "1y", "interval": "1d", "need_news": True,
        "news_query": "AAPL", "need_decision": True, "want_charts": True, "want_pdf": True, "want_csv": True,
        "analysis_goal": "Compare AAPL and MSFT", "report_title": "AAPL vs MSFT"}
def fake_json(messages, **kw):
    sysmsg = messages[0]["content"]
    if "memory curator" in sysmsg and "choose ONLY" in sysmsg: return {"ids": []}
    if "orchestrator" in sysmsg: return PLAN
    if "decision engine" in sysmsg: return {"stance": "hold", "headline": "Hold both", "confidence": "medium", "rationale": ["x"], "risks": ["y"], "portfolio_adjustments": []}
    if "extract durable" in sysmsg: return {"memories": [{"kind": "decision", "topic": "AAPL hold", "summary": "Told to hold AAPL", "tags": ["AAPL"]}], "holdings": [{"symbol": "AAPL", "quantity": 10}]}
    return {}
def fake_tools(messages, tools, **kw):
    s = messages[0]["content"]
    if "Kova" in s: return [("performance_summary", {"symbols": ["AAPL", "MSFT"]}), ("sharpe_ratio", {"symbol": "AAPL"}),
                            ("technical_indicators", {"symbol": "AAPL", "indicators": ["rsi", "macd", "bbands", "sma"]}),
                            ("correlation_matrix", {"symbols": ["AAPL", "MSFT"]}), ("max_drawdown", {"symbol": "MSFT"}),
                            ("value_at_risk", {"symbol": "AAPL"}), ("bogus_tool", {})]
    return [("candlestick_chart", {"symbol": "AAPL", "overlay_key": "indicators_AAPL", "title": "AAPL price"}),
            ("line_chart", {"series_key": "cumulative_returns", "columns": [], "title": "Cumulative returns"}),
            ("heatmap_chart", {"series_key": "correlation", "title": "Correlation"}),
            ("indicator_panel", {"series_key": "indicators_AAPL", "column": "RSI_14", "title": "RSI"})]
llm.chat_json, llm.chat_tools = fake_json, fake_tools
llm.chat = lambda messages, **kw: "**Hold both.** AAPL Sharpe looks fine; see #Graph-01."

DB = {"charts": [], "messages": [], "mem": [], "hold": [], "files": []}
repo.list_holdings = lambda uid: DB["hold"]
repo.memory_index = lambda uid, limit=150: []
repo.add_memory = lambda uid, chat, kind, topic, summary, tags: DB["mem"].append(topic)
repo.upsert_holding = lambda uid, sym, qty, price=None, **kw: DB["hold"].append(sym)
repo.next_chart_seq = lambda chat: len(DB["charts"]) + 1
repo.add_chart = lambda chat, uid, seq, title, kind, url, meta: DB["charts"].append(title) or {"tag": f"#Graph-{seq:02d}"}
def up(bucket, uid, data, ext, ct):
    DB["files"].append((ext, len(data))); open(f"/tmp/claude-0/smoke_{len(DB['files'])}.{ext}", "wb").write(data); return f"https://x/{ext}"
repo.upload_bytes = up
repo.get_chat = lambda c, u: {"id": c, "title": "New chat"}
repo.recent_messages = lambda *a, **k: []
repo.add_message = lambda chat, uid, role, content, meta=None: DB["messages"].append((role, content, meta)) or {"id": "m1", "content": content}
repo.get_charts_by_seq = lambda *a: []
repo.get_uploads = lambda *a: []
repo.update_chat = lambda *a, **k: None

import pipeline
events = []
os.makedirs("/tmp/claude-0", exist_ok=True)
pipeline.run_turn("c1", "u1", "Compare AAPL and MSFT, should I hold? Give me a PDF and CSV.", [], lambda k, d: events.append((k, d)))

for k, d in events:
    print(k, json.dumps(d)[:150])
print("\nDB:", {k: (v if k != "messages" else len(v)) for k, v in DB.items()})
final = [d for k, d in events if k == "message"][0]
assert "Not financial advice" in final["content"], "disclaimer missing"
assert len(final["meta"]["charts"]) == 4 and len(final["meta"]["files"]) == 2
assert DB["mem"] and DB["hold"] == ["AAPL"]
print("\nSMOKE TEST PASSED")
