"""Runs one user turn end-to-end and reports progress through emit(kind, data)."""
import gc
import re

import repo
from graph import get_graph

REF_RE = re.compile(r"#Graph-(\d+)", re.I)


def run_turn(chat_id: str, user_id: str, text: str, attachment_ids: list[str], emit):
    chat = repo.get_chat(chat_id, user_id)
    history = repo.recent_messages(chat_id, user_id, 6)
    user_msg = repo.add_message(chat_id, user_id, "user", text,
                                {"attachments": attachment_ids} if attachment_ids else {})
    refs = repo.get_charts_by_seq(chat_id, user_id, sorted({int(n) for n in REF_RE.findall(text)})[:5])
    attachments = repo.get_uploads(attachment_ids[:3], user_id)

    state = {"user_id": user_id, "chat_id": chat_id, "user_text": text, "history": history,
             "attachments": attachments, "ref_charts": refs, "done": []}
    result = get_graph().invoke(state, config={"configurable": {"emit": emit}, "recursion_limit": 40})

    meta = {"charts": result.get("charts") or [], "files": result.get("files") or []}
    if result.get("dimon"):
        meta["decision"] = {k: result["dimon"].get(k) for k in ("stance", "confidence", "headline")}
    answer = repo.add_message(chat_id, user_id, "assistant", result.get("final_text", ""), meta)

    if chat and chat.get("title") == "New chat":
        title = (text.strip().replace("\n", " ")[:48] or "New chat")
        repo.update_chat(chat_id, user_id, title=title)
        emit("title", {"title": title})
    else:
        repo.update_chat(chat_id, user_id)

    emit("message", {"id": answer["id"], "role": "assistant", "content": answer["content"], "meta": meta,
                     "user_message_id": user_msg["id"]})
    gc.collect()
