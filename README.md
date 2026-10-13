# FINIX AI

Multi-agent financial intelligence (hub-and-spoke on LangGraph, Groq LLM, Supabase, Render).

```
finix/
├─ render.yaml             Render blueprint (secrets typed in the dashboard)
├─ ENV_VARS.md             Every environment variable and what to put in it
├─ backend/
│  ├─ app.py               Flask entry: /api/*, /healthz, serves frontend/dist (SPA fallback)
│  ├─ auth.py              User register/login (hashed, Supabase) + admin login (env vars)
│  ├─ routes.py            Chats, uploads, SSE stream, portfolio, memory, admin overview
│  ├─ pipeline.py          One user turn: runs the graph, saves messages, emits SSE events
│  ├─ graph.py             LangGraph: Finix router hub + spokes
│  ├─ agents/              finix, rome, kova, dimon, frank, mike
│  ├─ tools/               rome_tools (raw fetch) · kova_tools (fixed maths) · mike_tools (charts/PDF/CSV)
│  ├─ repo.py              All Supabase access (tables + storage)
│  ├─ llm.py               Single Groq client (json / tool-calling / chat)
│  ├─ uploads.py           TXT / CSV / text-PDF parsing
│  ├─ schema.sql           Run once in Supabase SQL editor
│  ├─ gen_admin_hash.py    Makes ADMIN_n_PASSWORD_HASH values
│  └─ tests/smoke_test.py  Offline end-to-end test (no keys needed)
```

## Flow of one message
`frank_recall → finix_plan → router ⇄ {rome, kova, dimon, mike_charts, compose, mike_export} → frank_store`.
The router (Finix) is the only node that decides who runs next; spokes never call each other.

## API (all JSON, `Authorization: Bearer <token>`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | `{email,password}` → `{token,user}` |
| GET | `/api/auth/me` | current user |
| GET/POST | `/api/chats` | list / create chat |
| GET/PATCH/DELETE | `/api/chats/<id>` | messages+charts / rename / delete |
| POST | `/api/chats/<id>/upload` | multipart `file` (.txt .csv .pdf) → `{upload:{id,...}}` |
| POST | `/api/chats/<id>/stream` | `{message, attachment_ids?}` → **SSE** (see below) |
| GET | `/api/portfolio` | holdings + Frank's memory entries |
| PUT | `/api/portfolio/holdings` | upsert `{symbol,quantity,avg_price?,currency?}` |
| DELETE | `/api/portfolio/holdings/<symbol>` · `/api/memory/<id>` | remove |
| POST | `/api/admin/login` | `{username,password}` → admin token |
| GET | `/api/admin/overview` | counts, recent users, env var SET/unset flags |

### SSE events on `/stream` (read with `fetch` + stream reader, since it is a POST)
`start` · `trace {agent,msg}` (agent log console; ephemeral) · `chart {tag,seq,title,kind,url}` ·
`file {name,kind,url}` · `title {title}` · `message {id,content,meta}` · `error {message}` · `done`.

## Local test
```
cd backend && pip install -r requirements.txt && python -I tests/smoke_test.py
```
