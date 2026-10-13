# FINIX AI — Environment Variables (set in Render → your service → Environment)

No `.env` file is used anywhere. The app reads these from the process environment only.

## Required

| Name | What to put in it | Where to get it |
|---|---|---|
| `SECRET_KEY` | A long random string (64+ chars). Signs login tokens. If it changes, everyone is logged out. | `render.yaml` auto-generates it. Or run `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `SUPABASE_URL` | Your project URL, e.g. `https://abcdxyz.supabase.co` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | The **service_role** key (NOT the anon key). Server-side only; it bypasses RLS. | Supabase → Project Settings → API → `service_role` secret |
| `GROQ_API_KEY` | Your Groq API key (starts with `gsk_`) | console.groq.com → API Keys |
| `ADMIN_1_USERNAME` | The username you want for admin 1 | You choose |
| `ADMIN_1_PASSWORD` | The admin password in plain text (use 12+ characters). Change it any time in Render; the service restarts and the new one applies. | You choose |

## Optional

| Name | Default | What it does |
|---|---|---|
| `ADMIN_2_USERNAME` / `ADMIN_2_PASSWORD` | unset | Second admin (max two). Same as admin 1. |
| `ADMIN_n_PASSWORD_HASH` | unset | Alternative to `ADMIN_n_PASSWORD` if you prefer not to store plain text. Make it with `python gen_admin_hash.py`. Ignored if `ADMIN_n_PASSWORD` is set. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Model used by all six agents. |
| `TAVILY_API_KEY` | unset | Web search for Rome. Without it, Rome skips web searches. |
| `NEWSAPI_KEY` | unset | News for Rome. Without it, Rome skips news. |
| `PYTHON_VERSION` | `3.13.5` (set in render.yaml) | Python version Render builds with. |
| `CHARTS_BUCKET` | `charts` | Supabase Storage bucket for chart PNGs (must be public). |
| `EXPORTS_BUCKET` | `exports` | Supabase Storage bucket for PDF/CSV files (must be public). |
| `USER_TOKEN_TTL_HOURS` | `72` | How long a user login lasts. |
| `ADMIN_TOKEN_TTL_MINUTES` | `120` | How long an admin login lasts. |
| `MAX_UPLOAD_MB` | `5` | Max chat upload size. |

## Not env vars (but needed once)
1. Run `backend/schema.sql` in Supabase → SQL Editor (creates tables + the two storage buckets).
2. UptimeRobot: HTTP monitor on `https://<your-app>.onrender.com/healthz`, every 5 minutes.

## Notes
- Paste values with no surrounding quotes. Keep the repo private and never commit passwords to it.
- Chart and export files are stored in public buckets under unguessable random file names. Anyone with a link can open that file, but links aren't listed anywhere.
