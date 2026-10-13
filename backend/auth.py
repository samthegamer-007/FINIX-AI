"""User + admin authentication.

Users: email + password stored hashed (werkzeug, scrypt) in Supabase.
Admins: at most two, credentials live ONLY in Render env vars
(ADMIN_n_USERNAME / ADMIN_n_PASSWORD_HASH). No database row, no is_admin flag.
Tokens are signed, time-limited (itsdangerous); no server-side session store.
"""
import hmac
import re
import time
from functools import wraps

from flask import Blueprint, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import repo
from config import env, env_int

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# --- tiny in-memory brute-force guard (per process; fine for a single worker)
_FAILS: dict[str, list[float]] = {}
_WINDOW, _MAX_FAILS = 15 * 60, 8


def _blocked(key: str) -> bool:
    now = time.time()
    _FAILS[key] = [t for t in _FAILS.get(key, []) if now - t < _WINDOW]
    return len(_FAILS[key]) >= _MAX_FAILS


def _fail(key: str):
    _FAILS.setdefault(key, []).append(time.time())


def _ser(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(env("SECRET_KEY", required=True), salt=salt)


def _read(token: str, salt: str, max_age: int):
    try:
        return _ser(salt).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def _bearer() -> str | None:
    h = request.headers.get("Authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def require_user(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        tok = _bearer()
        data = _read(tok, "user", env_int("USER_TOKEN_TTL_HOURS", 72) * 3600) if tok else None
        if not data:
            return jsonify(error="unauthorized"), 401
        g.user_id = data["uid"]
        return fn(*a, **kw)
    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        tok = _bearer()
        data = _read(tok, "admin", env_int("ADMIN_TOKEN_TTL_MINUTES", 120) * 60) if tok else None
        if not data or not data.get("admin"):
            return jsonify(error="unauthorized"), 401
        g.admin = data["admin"]
        return fn(*a, **kw)
    return wrapper


# ------------------------------------------------------------------ user routes
@bp.post("/api/auth/register")
def register():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not EMAIL_RE.match(email):
        return jsonify(error="Enter a valid email address."), 400
    if len(password) < 8:
        return jsonify(error="Password must be at least 8 characters."), 400
    if repo.get_user_by_email(email):
        return jsonify(error="An account with this email already exists."), 409
    user = repo.create_user(email, generate_password_hash(password))
    token = _ser("user").dumps({"uid": user["id"]})
    return jsonify(token=token, user={"id": user["id"], "email": email}), 201


@bp.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    key = f"u:{request.remote_addr}:{email}"
    if _blocked(key):
        return jsonify(error="Too many attempts. Try again in a few minutes."), 429
    user = repo.get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        _fail(key)
        return jsonify(error="Invalid email or password."), 401
    token = _ser("user").dumps({"uid": user["id"]})
    return jsonify(token=token, user={"id": user["id"], "email": user["email"]})


@bp.get("/api/auth/me")
@require_user
def me():
    user = repo.get_user(g.user_id)
    if not user:
        return jsonify(error="unauthorized"), 401
    return jsonify(user=user)


# ------------------------------------------------------------------ admin routes
def _admin_accounts():
    """[(username, plain_password_or_None, hash_or_None)] for up to two admins.
    ADMIN_n_PASSWORD (plain text) is the simple option; ADMIN_n_PASSWORD_HASH also works
    and is used only if no plain password is set."""
    out = []
    for n in (1, 2):
        u = env(f"ADMIN_{n}_USERNAME")
        plain, h = env(f"ADMIN_{n}_PASSWORD"), env(f"ADMIN_{n}_PASSWORD_HASH")
        if u and (plain or h):
            out.append((u, plain, h))
    return out


def _password_ok(plain, hashed, supplied: str) -> bool:
    if plain:
        return hmac.compare_digest(plain.encode(), supplied.encode())
    return check_password_hash(hashed, supplied)


@bp.post("/api/admin/login")
def admin_login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", ""))
    password = str(body.get("password", ""))
    key = f"a:{request.remote_addr}"
    if _blocked(key):
        return jsonify(error="Too many attempts. Try again later."), 429
    matched = None
    for u, plain, h in _admin_accounts():
        # always evaluate both checks to keep timing uniform
        user_ok = hmac.compare_digest(u.encode(), username.encode())
        pass_ok = _password_ok(plain, h, password)
        if user_ok and pass_ok:
            matched = u
    if not matched:
        _fail(key)
        return jsonify(error="Invalid credentials."), 401
    return jsonify(token=_ser("admin").dumps({"admin": matched}))
