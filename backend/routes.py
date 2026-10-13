"""HTTP API (everything under /api). The React app is served by app.py."""
import json
import queue
import threading
import traceback

from flask import Blueprint, Response, g, jsonify, request, stream_with_context

import pipeline
import repo
import uploads
from auth import require_admin, require_user
from config import ALL_ENV_VARS, env

bp = Blueprint("api", __name__, url_prefix="/api")

_RUNNING: set[str] = set()          # user ids with a turn in flight (one at a time per user)
_RUN_LOCK = threading.Lock()


def _own_chat(chat_id):
    chat = repo.get_chat(chat_id, g.user_id)
    return chat


# ------------------------------------------------------------------ chats
@bp.get("/chats")
@require_user
def chats():
    return jsonify(chats=repo.list_chats(g.user_id))


@bp.post("/chats")
@require_user
def new_chat():
    return jsonify(chat=repo.create_chat(g.user_id)), 201


@bp.get("/chats/<chat_id>")
@require_user
def chat_detail(chat_id):
    chat = _own_chat(chat_id)
    if not chat:
        return jsonify(error="not found"), 404
    return jsonify(chat=chat, messages=repo.list_messages(chat_id, g.user_id),
                   charts=repo.list_charts(chat_id, g.user_id))


@bp.patch("/chats/<chat_id>")
@require_user
def rename_chat(chat_id):
    if not _own_chat(chat_id):
        return jsonify(error="not found"), 404
    title = str((request.get_json(silent=True) or {}).get("title", "")).strip()[:80]
    if not title:
        return jsonify(error="title required"), 400
    repo.update_chat(chat_id, g.user_id, title=title)
    return jsonify(ok=True)


@bp.delete("/chats/<chat_id>")
@require_user
def remove_chat(chat_id):
    repo.delete_chat(chat_id, g.user_id)
    return jsonify(ok=True)


# ------------------------------------------------------------------ uploads
@bp.post("/chats/<chat_id>/upload")
@require_user
def upload(chat_id):
    if not _own_chat(chat_id):
        return jsonify(error="not found"), 404
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="No file provided."), 400
    data = f.read(uploads.max_bytes() + 1)
    try:
        kind, text = uploads.parse_upload(f.filename, data)
    except uploads.UploadError as exc:
        return jsonify(error=str(exc)), 400
    row = repo.add_upload(g.user_id, chat_id, f.filename[:120], kind, text)
    return jsonify(upload={"id": row["id"], "filename": row["filename"], "kind": kind, "chars": len(text)}), 201


# ------------------------------------------------------------------ streaming turn (SSE over POST)
def _sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, default=str)}\n\n"


@bp.post("/chats/<chat_id>/stream")
@require_user
def stream(chat_id):
    body = request.get_json(silent=True) or {}
    text = str(body.get("message", "")).strip()
    attachment_ids = [str(i) for i in (body.get("attachment_ids") or [])][:3]
    if not text:
        return jsonify(error="Message is empty."), 400
    if len(text) > 4000:
        return jsonify(error="Message too long (max 4000 characters)."), 400
    if not _own_chat(chat_id):
        return jsonify(error="not found"), 404

    user_id = g.user_id
    with _RUN_LOCK:
        if user_id in _RUNNING:
            return jsonify(error="Finix is still working on your previous message."), 429
        _RUNNING.add(user_id)

    q: queue.Queue = queue.Queue()

    def emit(kind, data):
        q.put((kind, data))

    def worker():
        try:
            pipeline.run_turn(chat_id, user_id, text, attachment_ids, emit)
        except Exception as exc:
            traceback.print_exc()
            msg = "Something went wrong while processing that. Please try again."
            if "rate limit" in str(exc).lower() or "429" in str(exc):
                msg = "The AI provider is rate-limiting us right now. Wait a few seconds and try again."
            q.put(("error", {"message": msg}))
        finally:
            with _RUN_LOCK:
                _RUNNING.discard(user_id)
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        yield _sse("start", {"chat_id": chat_id})
        while True:
            try:
                item = q.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if item is None:
                yield _sse("done", {})
                return
            yield _sse(*item)

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


# ------------------------------------------------------------------ portfolio + Frank's memory view
@bp.get("/portfolio")
@require_user
def portfolio():
    return jsonify(holdings=repo.list_holdings(g.user_id), memory=repo.list_memory(g.user_id))


@bp.put("/portfolio/holdings")
@require_user
def put_holding():
    b = request.get_json(silent=True) or {}
    symbol = str(b.get("symbol", "")).strip().upper()
    try:
        qty = float(b.get("quantity"))
        price = float(b["avg_price"]) if b.get("avg_price") not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify(error="Quantity and average price must be numbers."), 400
    if not symbol or len(symbol) > 15 or qty < 0:
        return jsonify(error="Enter a ticker symbol and a non-negative quantity."), 400
    repo.upsert_holding(g.user_id, symbol, qty, price, str(b.get("asset_type") or "equity")[:20],
                        str(b.get("currency") or "USD")[:5].upper(), "manual")
    return jsonify(holdings=repo.list_holdings(g.user_id))


@bp.delete("/portfolio/holdings/<symbol>")
@require_user
def del_holding(symbol):
    repo.delete_holding(g.user_id, symbol)
    return jsonify(holdings=repo.list_holdings(g.user_id))


@bp.delete("/memory/<memory_id>")
@require_user
def del_memory(memory_id):
    repo.delete_memory(g.user_id, memory_id)
    return jsonify(ok=True)


# ------------------------------------------------------------------ admin
@bp.get("/admin/overview")
@require_admin
def admin_overview():
    counts = {t: repo.count(t) for t in ("users", "chats", "messages", "charts", "frank_memory", "portfolio_holdings")}
    return jsonify(
        admin=g.admin,
        counts=counts,
        recent_users=repo.recent_users(50),
        env_status={name: bool(env(name)) for name in ALL_ENV_VARS},   # set / not set, never values
        running_turns=len(_RUNNING),
    )
