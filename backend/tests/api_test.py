"""Offline API test with an in-memory repo. Run from backend/: python -I tests/api_test.py"""
import os, sys, io, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from werkzeug.security import generate_password_hash
os.environ.update(SECRET_KEY="test-secret", ADMIN_1_USERNAME="boss", ADMIN_1_PASSWORD="correct-horse-battery")
import repo
U, C = {}, {}
repo.get_user_by_email = lambda e: U.get(e)
def cu(e, h): U[e] = {"id": "u" + str(len(U)), "email": e, "password_hash": h}; return U[e]
repo.create_user = cu
repo.get_user = lambda i: next((u for u in U.values() if u["id"] == i), None)
repo.create_chat = lambda uid, title="New chat": C.setdefault("c1", {"id": "c1", "user_id": uid, "title": title})
repo.get_chat = lambda c, u: C.get(c) if C.get(c, {}).get("user_id") == u else None
repo.add_upload = lambda uid, chat, fn, kind, text: {"id": "up1", "filename": fn}
repo.count = lambda t: 1
repo.recent_users = lambda n=50: []
import pipeline
def fake_turn(chat_id, user_id, text, att, emit):
    emit("trace", {"agent": "Finix", "msg": "hi"}); emit("message", {"content": "ok"})
pipeline.run_turn = fake_turn
from app import app
c = app.test_client()
r = c.post("/api/auth/register", json={"email": "a@b.co", "password": "short"}); assert r.status_code == 400
r = c.post("/api/auth/register", json={"email": "a@b.co", "password": "longenough1"}); assert r.status_code == 201
tok = r.json["token"]; H = {"Authorization": f"Bearer {tok}"}
assert c.post("/api/auth/register", json={"email": "a@b.co", "password": "longenough1"}).status_code == 409
assert c.post("/api/auth/login", json={"email": "a@b.co", "password": "wrong"}).status_code == 401
assert c.post("/api/auth/login", json={"email": "a@b.co", "password": "longenough1"}).status_code == 200
assert c.get("/api/chats").status_code == 401
assert c.get("/api/auth/me", headers=H).json["user"]["email"] == "a@b.co"
assert c.post("/api/chats", headers=H).status_code == 201
r = c.post("/api/chats/c1/upload", headers=H, data={"file": (io.BytesIO(b"symbol,qty\nAAPL,10\n"), "h.csv")}); assert r.status_code == 201, r.json
assert c.post("/api/chats/c1/upload", headers=H, data={"file": (io.BytesIO(b"x"), "pic.png")}).status_code == 400
assert c.post("/api/chats/c1/stream", headers=H, json={"message": ""}).status_code == 400
r = c.post("/api/chats/c1/stream", headers=H, json={"message": "hello"})
body = r.get_data(as_text=True); assert "event: trace" in body and "event: message" in body and "event: done" in body, body
assert c.post("/api/chats/nope/stream", headers=H, json={"message": "hi"}).status_code == 404
assert c.get("/api/admin/overview", headers=H).status_code == 401           # user token is not an admin token
assert c.post("/api/admin/login", json={"username": "boss", "password": "bad"}).status_code == 401
t = c.post("/api/admin/login", json={"username": "boss", "password": "correct-horse-battery"}).json["token"]
ov = c.get("/api/admin/overview", headers={"Authorization": f"Bearer {t}"}); assert ov.status_code == 200
assert ov.json["env_status"]["ADMIN_1_USERNAME"] is True and "boss" not in json.dumps(ov.json["env_status"])
assert c.get("/auth").status_code == 200 and c.get("/healthz").json["status"] == "ok"
assert c.get("/api/nothing").status_code == 404
print("API TEST PASSED")

# hash variant still works when no plain password is set
os.environ.pop("ADMIN_1_PASSWORD"); os.environ["ADMIN_1_PASSWORD_HASH"] = generate_password_hash("hashed-pass-123")
assert c.post("/api/admin/login", json={"username": "boss", "password": "hashed-pass-123"}).status_code == 200
assert c.post("/api/admin/login", json={"username": "boss", "password": "correct-horse-battery"}).status_code == 401
print("HASH VARIANT PASSED")
