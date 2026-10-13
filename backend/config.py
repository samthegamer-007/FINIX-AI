"""Central configuration. Every secret is read from the process environment
(Render Environment Variables). No .env files are used or loaded."""
import os


def env(name: str, default=None, required: bool = False):
    value = os.environ.get(name, default)
    if required and (value is None or str(value).strip() == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Names of every env var the app understands (used by the admin dashboard to
# show which ones are SET, never their values).
ALL_ENV_VARS = [
    "SECRET_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "TAVILY_API_KEY",
    "NEWSAPI_KEY",
    "ADMIN_1_USERNAME",
    "ADMIN_1_PASSWORD",
    "ADMIN_1_PASSWORD_HASH",
    "ADMIN_2_USERNAME",
    "ADMIN_2_PASSWORD",
    "ADMIN_2_PASSWORD_HASH",
    "CHARTS_BUCKET",
    "EXPORTS_BUCKET",
    "USER_TOKEN_TTL_HOURS",
    "ADMIN_TOKEN_TTL_MINUTES",
    "MAX_UPLOAD_MB",
]

DISCLAIMER = "Informational. Not financial advice."

ALLOWED_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"}
ALLOWED_INTERVALS = {"1d", "1wk", "1mo"}
MAX_SYMBOLS = 5
