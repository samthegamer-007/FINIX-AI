"""All Supabase access lives here (tables + storage), so the rest of the app
never touches the client directly."""
import threading
import uuid
from datetime import datetime, timezone

from config import env

_client = None
_lock = threading.Lock()


def sb():
    global _client
    with _lock:
        if _client is None:
            from supabase import create_client
            _client = create_client(
                env("SUPABASE_URL", required=True),
                env("SUPABASE_SERVICE_KEY", required=True),
            )
        return _client


def _now():
    return datetime.now(timezone.utc).isoformat()


def _rows(res):
    return res.data or []


# ---------------------------------------------------------------- users
def create_user(email: str, password_hash: str):
    return _rows(sb().table("users").insert({"email": email, "password_hash": password_hash}).execute())[0]


def get_user_by_email(email: str):
    rows = _rows(sb().table("users").select("*").eq("email", email).limit(1).execute())
    return rows[0] if rows else None


def get_user(user_id: str):
    rows = _rows(sb().table("users").select("id,email,created_at").eq("id", user_id).limit(1).execute())
    return rows[0] if rows else None


# ---------------------------------------------------------------- chats
def create_chat(user_id: str, title: str = "New chat"):
    return _rows(sb().table("chats").insert({"user_id": user_id, "title": title}).execute())[0]


def list_chats(user_id: str):
    return _rows(
        sb().table("chats").select("id,title,created_at,updated_at")
        .eq("user_id", user_id).order("updated_at", desc=True).limit(100).execute()
    )


def get_chat(chat_id: str, user_id: str):
    rows = _rows(sb().table("chats").select("*").eq("id", chat_id).eq("user_id", user_id).limit(1).execute())
    return rows[0] if rows else None


def update_chat(chat_id: str, user_id: str, **fields):
    fields["updated_at"] = _now()
    sb().table("chats").update(fields).eq("id", chat_id).eq("user_id", user_id).execute()


def delete_chat(chat_id: str, user_id: str):
    sb().table("chats").delete().eq("id", chat_id).eq("user_id", user_id).execute()


# ---------------------------------------------------------------- messages
def add_message(chat_id: str, user_id: str, role: str, content: str, meta: dict | None = None):
    return _rows(
        sb().table("messages").insert(
            {"chat_id": chat_id, "user_id": user_id, "role": role, "content": content, "meta": meta or {}}
        ).execute()
    )[0]


def list_messages(chat_id: str, user_id: str, limit: int = 500):
    return _rows(
        sb().table("messages").select("id,role,content,meta,created_at")
        .eq("chat_id", chat_id).eq("user_id", user_id).order("created_at").limit(limit).execute()
    )


def recent_messages(chat_id: str, user_id: str, n: int = 6):
    rows = _rows(
        sb().table("messages").select("role,content")
        .eq("chat_id", chat_id).eq("user_id", user_id).order("created_at", desc=True).limit(n).execute()
    )
    return list(reversed(rows))


# ---------------------------------------------------------------- charts
def next_chart_seq(chat_id: str) -> int:
    rows = _rows(sb().table("charts").select("seq").eq("chat_id", chat_id).order("seq", desc=True).limit(1).execute())
    return (rows[0]["seq"] + 1) if rows else 1


def add_chart(chat_id: str, user_id: str, seq: int, title: str, kind: str, url: str, meta: dict):
    return _rows(
        sb().table("charts").insert(
            {"chat_id": chat_id, "user_id": user_id, "seq": seq, "tag": f"#Graph-{seq:02d}",
             "title": title, "kind": kind, "url": url, "meta": meta}
        ).execute()
    )[0]


def list_charts(chat_id: str, user_id: str):
    return _rows(
        sb().table("charts").select("seq,tag,title,kind,url,meta,created_at")
        .eq("chat_id", chat_id).eq("user_id", user_id).order("seq").execute()
    )


def get_charts_by_seq(chat_id: str, user_id: str, seqs: list[int]):
    if not seqs:
        return []
    return _rows(
        sb().table("charts").select("seq,tag,title,kind,url,meta")
        .eq("chat_id", chat_id).eq("user_id", user_id).in_("seq", seqs).execute()
    )


# ---------------------------------------------------------------- uploads
def add_upload(user_id: str, chat_id: str, filename: str, kind: str, content_text: str):
    return _rows(
        sb().table("uploads").insert(
            {"user_id": user_id, "chat_id": chat_id, "filename": filename, "kind": kind, "content_text": content_text}
        ).execute()
    )[0]


def get_uploads(ids: list[str], user_id: str):
    if not ids:
        return []
    return _rows(
        sb().table("uploads").select("id,filename,kind,content_text")
        .in_("id", ids).eq("user_id", user_id).execute()
    )


# ---------------------------------------------------------------- portfolio
def list_holdings(user_id: str):
    return _rows(
        sb().table("portfolio_holdings").select("symbol,asset_type,quantity,avg_price,currency,source,updated_at")
        .eq("user_id", user_id).order("symbol").execute()
    )


def upsert_holding(user_id: str, symbol: str, quantity: float, avg_price=None,
                   asset_type: str = "equity", currency: str = "USD", source: str = "manual"):
    sb().table("portfolio_holdings").upsert(
        {"user_id": user_id, "symbol": symbol.upper(), "quantity": quantity, "avg_price": avg_price,
         "asset_type": asset_type, "currency": currency, "source": source, "updated_at": _now()},
        on_conflict="user_id,symbol",
    ).execute()


def delete_holding(user_id: str, symbol: str):
    sb().table("portfolio_holdings").delete().eq("user_id", user_id).eq("symbol", symbol.upper()).execute()


# ---------------------------------------------------------------- Frank memory
def add_memory(user_id: str, chat_id: str | None, kind: str, topic: str, summary: str, tags: list[str]):
    sb().table("frank_memory").insert(
        {"user_id": user_id, "chat_id": chat_id, "kind": kind, "topic": topic, "summary": summary, "tags": tags}
    ).execute()


def memory_index(user_id: str, limit: int = 150):
    """Headlines only — cheap to scan. Full entries are fetched by id."""
    return _rows(
        sb().table("frank_memory").select("id,kind,topic,tags,created_at")
        .eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    )


def memory_by_ids(user_id: str, ids: list[str]):
    if not ids:
        return []
    return _rows(
        sb().table("frank_memory").select("id,kind,topic,summary,tags,created_at")
        .eq("user_id", user_id).in_("id", ids).execute()
    )


def list_memory(user_id: str, limit: int = 200):
    return _rows(
        sb().table("frank_memory").select("id,kind,topic,summary,tags,created_at")
        .eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    )


def delete_memory(user_id: str, memory_id: str):
    sb().table("frank_memory").delete().eq("user_id", user_id).eq("id", memory_id).execute()


# ---------------------------------------------------------------- storage
def upload_bytes(bucket: str, user_id: str, data: bytes, ext: str, content_type: str) -> str:
    path = f"{user_id}/{uuid.uuid4().hex}.{ext}"
    sb().storage.from_(bucket).upload(path, data, {"content-type": content_type})
    return sb().storage.from_(bucket).get_public_url(path)


# ---------------------------------------------------------------- admin stats
def count(table: str) -> int:
    res = sb().table(table).select("id", count="exact").limit(1).execute()
    return res.count or 0


def recent_users(limit: int = 50):
    return _rows(sb().table("users").select("id,email,created_at").order("created_at", desc=True).limit(limit).execute())
