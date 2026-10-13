"""Agent 5 — Frank: long-term memory. Frank has NO brokerage connection; holdings
are only what the user declared (manually, or stated in chat).

recall(): scans compact memory headlines and picks only what is relevant to the
prompt (never dumps the whole memory). store(): distils the finished exchange
into condensed entries."""
import re

import llm
import repo
from agents.common import compact, trace

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")


def recall(state, config):
    uid, text = state["user_id"], state["user_text"]
    trace(config, "Frank", "Checking memory and declared portfolio...")
    holdings = repo.list_holdings(uid)
    index = repo.memory_index(uid)
    memory_ctx = ""
    if index:
        lines = [f"{m['id']} | {m['kind']} | {m['topic']} | {','.join(m.get('tags') or [])}" for m in index]
        data = llm.chat_json([
            {"role": "system", "content":
                "You are Frank, a memory curator. From the memory headlines, choose ONLY the entries that "
                "would materially help answer the user's new message. Return JSON: {\"ids\": [up to 6 ids]}. "
                "Return {\"ids\": []} if none are relevant."},
            {"role": "user", "content": f"User message: {text[:600]}\n\nHeadlines (id | kind | topic | tags):\n" + "\n".join(lines)},
        ], max_tokens=300)
        valid = {m["id"] for m in index}
        ids = [i for i in (data.get("ids") or []) if i in valid][:6]
        entries = repo.memory_by_ids(uid, ids)
        if entries:
            memory_ctx = "\n".join(f"- [{e['kind']}] {e['topic']}: {e['summary']}" for e in entries)
    trace(config, "Frank", f"Recalled {memory_ctx.count(chr(10)) + 1 if memory_ctx else 0} memory item(s); "
                           f"{len(holdings)} declared holding(s).")
    return {"memory_ctx": memory_ctx, "holdings": holdings}


def store(state, config):
    uid, chat_id = state["user_id"], state["chat_id"]
    plan = state.get("plan") or {}
    text, answer = state["user_text"], state.get("final_text", "")
    if plan.get("intent") == "chitchat" and len(text) < 40:
        return {}
    trace(config, "Frank", "Filing what matters from this exchange...")
    data = llm.chat_json([
        {"role": "system", "content":
            "You are Frank, a memory curator for a financial assistant. From this exchange extract durable "
            "items worth remembering long-term. Return JSON: "
            "{\"memories\": [{\"kind\": \"fact|decision|preference|holding_note\", \"topic\": \"short headline\", "
            "\"summary\": \"one or two condensed sentences\", \"tags\": [\"tickers or themes\"]}], "
            "\"holdings\": [{\"symbol\": \"TICKER\", \"quantity\": number, \"avg_price\": number or null, \"currency\": \"USD\"}]}. "
            "Rules: max 3 memories. Store only things the USER stated (goals, risk tolerance, constraints, "
            "preferences) or recommendations the assistant made (kind=decision, with ticker and stance). "
            "'holdings' ONLY if the user explicitly declared what they own. Never invent. Empty lists are fine."},
        {"role": "user", "content": f"USER: {text[:800]}\n\nASSISTANT: {answer[:1500]}"},
    ], max_tokens=700)
    saved = 0
    for m in (data.get("memories") or [])[:3]:
        if isinstance(m, dict) and m.get("topic") and m.get("summary"):
            tags = [str(t)[:20] for t in (m.get("tags") or [])][:6]
            kind = m.get("kind") if m.get("kind") in ("fact", "decision", "preference", "holding_note") else "fact"
            repo.add_memory(uid, chat_id, kind, str(m["topic"])[:120], str(m["summary"])[:500], tags)
            saved += 1
    for h in (data.get("holdings") or [])[:20]:
        try:
            sym = str(h["symbol"]).upper().strip()
            qty = float(h["quantity"])
            if SYMBOL_RE.match(sym) and qty >= 0:
                price = h.get("avg_price")
                repo.upsert_holding(uid, sym, qty, float(price) if price is not None else None,
                                    currency=str(h.get("currency") or "USD")[:5], source="chat")
        except (KeyError, TypeError, ValueError):
            continue
    if saved:
        trace(config, "Frank", f"Stored {saved} memory item(s).")
    return {}
