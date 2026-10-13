"""Turn a user upload (TXT / CSV / text-based PDF) into plain text for the LLM.
Images and scanned PDFs are rejected in the MVP (the Groq text model cannot read them)."""
import io

from config import env_int

MAX_CHARS = 12000
ALLOWED = {"txt": "txt", "csv": "csv", "pdf": "pdf"}


class UploadError(ValueError):
    pass


def max_bytes() -> int:
    return env_int("MAX_UPLOAD_MB", 5) * 1024 * 1024


def parse_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Returns (kind, text). Raises UploadError with a user-facing message."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise UploadError("Only .txt, .csv and text-based .pdf files are supported right now.")
    if len(data) > max_bytes():
        raise UploadError(f"File too large (max {env_int('MAX_UPLOAD_MB', 5)} MB).")
    kind = ALLOWED[ext]
    if kind == "txt":
        text = data.decode("utf-8", errors="replace")
    elif kind == "csv":
        text = _csv_summary(data)
    else:
        text = _pdf_text(data)
    text = text.strip()
    if not text:
        raise UploadError("No readable text found in that file.")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n...[truncated]"
    return kind, text


def _csv_summary(data: bytes) -> str:
    import pandas as pd
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception:
        raise UploadError("Could not parse that CSV file.")
    parts = [
        f"CSV with {len(df)} rows and {len(df.columns)} columns.",
        "Columns: " + ", ".join(map(str, df.columns)),
        "First rows:\n" + df.head(15).to_csv(index=False),
    ]
    num = df.select_dtypes("number")
    if not num.empty:
        parts.append("Numeric summary:\n" + num.describe().round(4).to_string())
    return "\n\n".join(parts)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:40]:
            pages.append(page.extract_text() or "")
            if sum(len(p) for p in pages) > MAX_CHARS:
                break
    except Exception:
        raise UploadError("Could not read that PDF.")
    text = "\n".join(pages)
    if len(text.strip()) < 20:
        raise UploadError("That PDF has no extractable text (it may be scanned). Scanned PDFs aren't supported yet.")
    return text
