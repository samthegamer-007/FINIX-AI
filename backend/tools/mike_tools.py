"""Mike's FIXED tool library: static chart rendering (matplotlib / seaborn /
mplfinance, Obsidian & Mint theme), CSV export and fpdf2 PDF assembly.
Mike never calculates: every series it draws comes from Kova (or raw Rome prices)."""
import io
import re
from dataclasses import dataclass
from typing import Callable, Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

BG, SURFACE, BORDER = "#0B0F12", "#161E24", "#24303A"
MINT, MUTED, RED = "#00E699", "#8A9BA8", "#FF4D4D"
PALETTE = [MINT, "#4DA3FF", "#FFB84D", "#C77DFF", "#FF7AA8", "#7DE3F4"]


def _style():
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": SURFACE, "savefig.facecolor": BG,
        "axes.edgecolor": BORDER, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
        "text.color": "#E6EDF3", "axes.titlecolor": "#E6EDF3", "grid.color": BORDER, "grid.alpha": 0.6,
        "axes.grid": True, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    })


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


@dataclass
class Assets:
    """What Mike can draw from. Filled by the graph from Rome + Kova output."""
    series: dict[str, pd.DataFrame]       # key -> frame (Kova series, plus ohlc_<SYMBOL> from Rome)
    tables: dict[str, dict]               # key -> dict (e.g. allocation)


@dataclass
class ChartResult:
    png: bytes
    title: str
    kind: str
    meta: dict


# ----------------------------------------------------------------- argument schemas
class LineArgs(BaseModel):
    series_key: str = Field(description="Key of an available series, e.g. cumulative_returns or portfolio_cumulative")
    columns: list[str] = Field(default_factory=list, description="Columns to plot; empty = all")
    title: str


class CandleArgs(BaseModel):
    symbol: str
    overlay_key: str | None = Field(None, description="Optional indicators_<SYMBOL> series key for SMA/EMA/Bollinger overlays")
    title: str


class PieArgs(BaseModel):
    table_key: str = Field(description="Key of an available table of label->weight, e.g. allocation")
    title: str


class HistArgs(BaseModel):
    series_key: str = Field(description="Key of a series, e.g. returns_AAPL")
    column: str
    title: str


class HeatArgs(BaseModel):
    series_key: str = Field(description="Key of a matrix series, e.g. correlation")
    title: str


class LowerPanelArgs(BaseModel):
    series_key: str = Field(description="indicators_<SYMBOL> key")
    column: Literal["RSI_14", "MACDh_12_26_9"] = "RSI_14"
    title: str


# ----------------------------------------------------------------- chart tools
def line_chart(assets: Assets, a: LineArgs) -> ChartResult:
    df = _get(assets, a.series_key)
    cols = [c for c in a.columns if c in df.columns] or list(df.columns)
    _style()
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for i, c in enumerate(cols[:6]):
        ax.plot(df.index, df[c], color=PALETTE[i % len(PALETTE)], lw=1.8, label=str(c))
    if len(cols) > 1:
        ax.legend(frameon=False, labelcolor="#E6EDF3")
    ax.set_title(a.title, loc="left", fontweight="bold")
    fig.autofmt_xdate()
    return ChartResult(_png(fig), a.title, "line", {"series_key": a.series_key, "columns": cols})


def candlestick_chart(assets: Assets, a: CandleArgs) -> ChartResult:
    import mplfinance as mpf
    sym = a.symbol.upper()
    ohlc = _get(assets, f"ohlc_{sym}").tail(180)
    add = []
    if a.overlay_key and a.overlay_key in assets.series:
        ov = assets.series[a.overlay_key].reindex(ohlc.index)
        colors = {"SMA_20": "#FFB84D", "SMA_50": "#4DA3FF", "EMA_20": "#C77DFF",
                  "BB_upper": MUTED, "BB_lower": MUTED, "BB_mid": BORDER}
        for c, col in colors.items():
            if c in ov.columns and ov[c].notna().any():
                add.append(mpf.make_addplot(ov[c], color=col, width=1.0))
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mpf.make_marketcolors(up=MINT, down=RED, edge="inherit", wick="inherit", volume="inherit"),
        facecolor=SURFACE, figcolor=BG, edgecolor=BORDER, gridcolor=BORDER)
    kwargs = {"addplot": add} if add else {}      # mplfinance rejects addplot=None
    fig, _ = mpf.plot(ohlc, type="candle", style=style, volume=True, title=a.title,
                      returnfig=True, figsize=(9, 5.4), warn_too_much_data=10000, **kwargs)
    return ChartResult(_png(fig), a.title, "candlestick", {"symbol": sym, "overlay_key": a.overlay_key})


def pie_chart(assets: Assets, a: PieArgs) -> ChartResult:
    tbl = {k: v for k, v in assets.tables.get(a.table_key, {}).items() if isinstance(v, (int, float)) and v}
    if not tbl:
        raise ValueError(f"Table {a.table_key} not available")
    _style()
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    ax.pie(list(tbl.values()), labels=list(tbl.keys()), autopct="%1.1f%%", startangle=90,
           colors=PALETTE * 3, textprops={"color": "#E6EDF3"}, wedgeprops={"edgecolor": BG, "linewidth": 2})
    ax.set_title(a.title, fontweight="bold")
    return ChartResult(_png(fig), a.title, "pie", {"table_key": a.table_key})


def histogram_chart(assets: Assets, a: HistArgs) -> ChartResult:
    import seaborn as sns
    df = _get(assets, a.series_key)
    if a.column not in df.columns:
        raise ValueError(f"Column {a.column} not in {a.series_key}")
    _style()
    fig, ax = plt.subplots(figsize=(8, 4.4))
    sns.histplot(df[a.column].dropna(), bins=40, color=MINT, edgecolor=BG, kde=True, ax=ax)
    ax.set_title(a.title, loc="left", fontweight="bold")
    return ChartResult(_png(fig), a.title, "histogram", {"series_key": a.series_key, "column": a.column})


def heatmap_chart(assets: Assets, a: HeatArgs) -> ChartResult:
    import seaborn as sns
    df = _get(assets, a.series_key)
    _style()
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    sns.heatmap(df, annot=True, fmt=".2f", cmap=sns.diverging_palette(10, 160, as_cmap=True), center=0,
                vmin=-1, vmax=1, linewidths=1, linecolor=BG, cbar=False, ax=ax)
    ax.set_title(a.title, loc="left", fontweight="bold")
    ax.grid(False)
    return ChartResult(_png(fig), a.title, "heatmap", {"series_key": a.series_key})


def indicator_panel(assets: Assets, a: LowerPanelArgs) -> ChartResult:
    df = _get(assets, a.series_key)
    if a.column not in df.columns:
        raise ValueError(f"Column {a.column} not in {a.series_key}")
    _style()
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(df.index, df[a.column], color=MINT, lw=1.6)
    if a.column == "RSI_14":
        ax.axhline(70, color=RED, lw=0.8, ls="--")
        ax.axhline(30, color=MINT, lw=0.8, ls="--")
        ax.set_ylim(0, 100)
    ax.set_title(a.title, loc="left", fontweight="bold")
    fig.autofmt_xdate()
    return ChartResult(_png(fig), a.title, "indicator", {"series_key": a.series_key, "column": a.column})


def _get(assets: Assets, key: str) -> pd.DataFrame:
    if key not in assets.series:
        raise ValueError(f"Series '{key}' not available. Have: {', '.join(assets.series)}")
    return assets.series[key]


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable


CHART_TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("line_chart", "Line chart of a series (cumulative returns, portfolio growth, drawdown).", LineArgs, line_chart),
    Tool("candlestick_chart", "OHLC candlestick chart with volume for a symbol, optionally with indicator overlays.", CandleArgs, candlestick_chart),
    Tool("pie_chart", "Pie chart of portfolio allocation weights.", PieArgs, pie_chart),
    Tool("histogram_chart", "Histogram of a return series.", HistArgs, histogram_chart),
    Tool("heatmap_chart", "Heatmap of a correlation matrix.", HeatArgs, heatmap_chart),
    Tool("indicator_panel", "RSI or MACD histogram panel for a symbol.", LowerPanelArgs, indicator_panel),
]}


def groq_tool_specs() -> list[dict]:
    specs = []
    for t in CHART_TOOLS.values():
        schema = t.args.model_json_schema()
        schema.pop("title", None)
        specs.append({"type": "function", "function": {"name": t.name, "description": t.description, "parameters": schema}})
    return specs


def run_chart_tool(name: str, raw_args: dict, assets: Assets) -> ChartResult:
    tool = CHART_TOOLS.get(name)
    if not tool:
        raise ValueError(f"Unknown chart tool {name}")
    return tool.fn(assets, tool.args(**raw_args))


# ----------------------------------------------------------------- exports
def generate_csv(assets: Assets) -> bytes:
    """One CSV: every Kova table flattened, then each series (date-indexed) as sections."""
    out = io.StringIO()
    for key, tbl in assets.tables.items():
        out.write(f"# table: {key}\n")
        pd.DataFrame(tbl).to_csv(out) if _is_nested(tbl) else pd.Series(tbl, name="value").to_csv(out)
        out.write("\n")
    for key, df in assets.series.items():
        if key.startswith("ohlc_"):
            continue
        out.write(f"# series: {key}\n")
        df.round(6).to_csv(out)
        out.write("\n")
    return out.getvalue().encode("utf-8")


def _is_nested(d: dict) -> bool:
    return bool(d) and all(isinstance(v, dict) for v in d.values())


def _latin(s: str) -> str:
    """fpdf2 core fonts are latin-1; replace what they cannot render."""
    repl = {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-",
            "•": "-", "₹": "Rs ", "…": "...", "→": "->"}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _plain_md(s: str) -> str:
    s = s.lstrip("#> ").replace("`", "")          # heading / quote markers only at line start
    s = re.sub(r"(\*\*|__)", "", s)               # bold markers
    s = re.sub(r"(?<![\w])[*_](?=\S)|(?<=\S)[*_](?![\w])", "", s)   # italic markers, keep snake_case
    return _latin(s)


def generate_pdf(title: str, body_markdown: str, chart_pngs: list[tuple[str, bytes]], disclaimer: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_fill_color(11, 15, 18)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_xy(10, 8)
    pdf.set_text_color(0, 230, 153)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 8, "FINIX AI")
    pdf.set_xy(10, 17)
    pdf.set_text_color(138, 155, 168)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _latin(title))
    pdf.set_xy(10, 34)
    pdf.set_text_color(30, 30, 30)

    for raw in body_markdown.splitlines():
        line = raw.strip()
        if not line:
            pdf.ln(2)
            continue
        if line.startswith("#"):
            pdf.set_font("Helvetica", "B", 12)
            pdf.ln(2)
            pdf.multi_cell(0, 6, _plain_md(line), new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5.2, _plain_md(line), new_x="LMARGIN", new_y="NEXT")

    for tag, png in chart_pngs:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _latin(tag), new_x="LMARGIN", new_y="NEXT")
        pdf.image(io.BytesIO(png), x=10, w=190)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(110, 110, 110)
    pdf.ln(6)
    pdf.multi_cell(0, 4, _latin(disclaimer), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
