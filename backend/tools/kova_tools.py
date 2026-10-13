"""Kova's FIXED tool library. The LLM only chooses a tool + arguments (Pydantic
schemas below); all maths is plain pandas / pandas-ta / quantstats code.

Each tool receives a Ctx (price frames, holdings, periods-per-year) and returns
a ToolOutput: a small JSON-safe `summary` for the LLM, plus optional `series`
(DataFrames) and `tables` (dicts) that Mike can chart/export by key.
"""
from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


@dataclass
class Ctx:
    frames: dict[str, pd.DataFrame]          # symbol -> OHLCV frame indexed by date
    holdings: list[dict]                     # declared holdings (may be empty)
    periods: int = 252                       # trading periods per year for the data interval


@dataclass
class ToolOutput:
    summary: dict
    series: dict[str, pd.DataFrame] = field(default_factory=dict)
    tables: dict[str, dict] = field(default_factory=dict)


# ----------------------------------------------------------------- helpers
def _close(ctx: Ctx, symbol: str) -> pd.Series:
    key = symbol.upper()
    if key not in ctx.frames:
        raise ValueError(f"No data for {symbol}. Available: {', '.join(ctx.frames) or 'none'}")
    return ctx.frames[key]["Close"].dropna()


def _returns(ctx: Ctx, symbol: str) -> pd.Series:
    r = _close(ctx, symbol).pct_change().dropna()
    if len(r) < 10:
        raise ValueError(f"Not enough data points for {symbol} ({len(r)}).")
    return r


def _f(x, nd=4):
    try:
        x = float(x)
    except Exception:
        return None
    return None if (x != x or x in (float("inf"), float("-inf"))) else round(x, nd)


def _qs():
    import quantstats as qs
    return qs.stats


# ----------------------------------------------------------------- argument schemas
class SymbolArgs(BaseModel):
    symbol: str = Field(description="Ticker symbol exactly as present in the fetched data, e.g. AAPL or RELIANCE.NS")


class SharpeArgs(SymbolArgs):
    risk_free_rate: float = Field(0.0, description="Annual risk-free rate as a decimal, e.g. 0.04")


class VarArgs(SymbolArgs):
    confidence: float = Field(0.95, description="Confidence level between 0.9 and 0.99")


class SymbolsArgs(BaseModel):
    symbols: list[str] = Field(description="Ticker symbols present in the fetched data")


class IndicatorArgs(SymbolArgs):
    indicators: list[Literal["rsi", "macd", "bbands", "sma", "ema"]] = Field(
        description="Technical indicators to compute and overlay")


class PortfolioArgs(BaseModel):
    pass


# ----------------------------------------------------------------- tools
def performance_summary(ctx: Ctx, a: SymbolsArgs) -> ToolOutput:
    qs = _qs()
    rows, cum = {}, {}
    for s in a.symbols:
        r = _returns(ctx, s)
        rows[s.upper()] = {
            "total_return": _f((1 + r).prod() - 1),
            "cagr": _f(qs.cagr(r, periods=ctx.periods)),
            "annual_volatility": _f(qs.volatility(r, periods=ctx.periods)),
            "best_period": _f(r.max()), "worst_period": _f(r.min()),
            "last_close": _f(_close(ctx, s).iloc[-1], 2),
        }
        cum[s.upper()] = (1 + r).cumprod() - 1
    cum_df = pd.DataFrame(cum).dropna(how="all")
    return ToolOutput({"performance": rows}, series={"cumulative_returns": cum_df}, tables={"performance": rows})


def sharpe_ratio(ctx: Ctx, a: SharpeArgs) -> ToolOutput:
    v = _qs().sharpe(_returns(ctx, a.symbol), rf=a.risk_free_rate, periods=ctx.periods)
    return ToolOutput({"symbol": a.symbol.upper(), "sharpe_ratio": _f(v, 3), "risk_free_rate": a.risk_free_rate})


def sortino_ratio(ctx: Ctx, a: SharpeArgs) -> ToolOutput:
    v = _qs().sortino(_returns(ctx, a.symbol), rf=a.risk_free_rate, periods=ctx.periods)
    return ToolOutput({"symbol": a.symbol.upper(), "sortino_ratio": _f(v, 3), "risk_free_rate": a.risk_free_rate})


def max_drawdown(ctx: Ctx, a: SymbolArgs) -> ToolOutput:
    r = _returns(ctx, a.symbol)
    nav = (1 + r).cumprod()
    dd = nav / nav.cummax() - 1
    return ToolOutput(
        {"symbol": a.symbol.upper(), "max_drawdown": _f(_qs().max_drawdown(r)),
         "current_drawdown": _f(dd.iloc[-1]), "trough_date": str(dd.idxmin())[:10]},
        series={f"drawdown_{a.symbol.upper()}": dd.to_frame("drawdown")})


def value_at_risk(ctx: Ctx, a: VarArgs) -> ToolOutput:
    r = _returns(ctx, a.symbol)
    conf = min(max(a.confidence, 0.9), 0.99)
    return ToolOutput({"symbol": a.symbol.upper(), "confidence": conf,
                       "value_at_risk_single_period": _f(_qs().value_at_risk(r, sigma=1, confidence=conf)),
                       "note": "Historical/parametric 1-period VaR; negative = loss."},
                      series={f"returns_{a.symbol.upper()}": r.to_frame("returns")})


def technical_indicators(ctx: Ctx, a: IndicatorArgs) -> ToolOutput:
    import pandas_ta as ta
    sym = a.symbol.upper()
    df = ctx.frames[sym] if sym in ctx.frames else None
    if df is None:
        raise ValueError(f"No data for {a.symbol}")
    close = df["Close"].dropna()
    out = pd.DataFrame(index=close.index)
    latest: dict = {}
    for ind in a.indicators:
        if ind == "rsi":
            out["RSI_14"] = ta.rsi(close, length=14)
            v = out["RSI_14"].dropna().iloc[-1]
            latest["rsi_14"] = _f(v, 2)
            latest["rsi_signal"] = "overbought" if v >= 70 else "oversold" if v <= 30 else "neutral"
        elif ind == "macd":
            m = ta.macd(close)
            for c in m.columns:
                out[c] = m[c]
            line, sig = m.iloc[:, 0].dropna().iloc[-1], m.iloc[:, 2].dropna().iloc[-1]
            latest.update(macd=_f(line), macd_signal_line=_f(sig), macd_view="bullish" if line > sig else "bearish")
        elif ind == "bbands":
            b = ta.bbands(close, length=20)
            lo = next(c for c in b.columns if c.startswith("BBL"))
            mid = next(c for c in b.columns if c.startswith("BBM"))
            up = next(c for c in b.columns if c.startswith("BBU"))
            out["BB_lower"], out["BB_mid"], out["BB_upper"] = b[lo], b[mid], b[up]
            last = close.iloc[-1]
            latest.update(bb_lower=_f(b[lo].iloc[-1], 2), bb_upper=_f(b[up].iloc[-1], 2),
                          bb_position="above upper" if last > b[up].iloc[-1] else
                          "below lower" if last < b[lo].iloc[-1] else "inside bands")
        elif ind == "sma":
            out["SMA_20"], out["SMA_50"] = ta.sma(close, 20), ta.sma(close, 50)
            latest.update(sma_20=_f(out["SMA_20"].iloc[-1], 2), sma_50=_f(out["SMA_50"].iloc[-1], 2))
        elif ind == "ema":
            out["EMA_20"] = ta.ema(close, 20)
            latest["ema_20"] = _f(out["EMA_20"].iloc[-1], 2)
    latest["last_close"] = _f(close.iloc[-1], 2)
    return ToolOutput({"symbol": sym, "latest": latest}, series={f"indicators_{sym}": out})


def correlation_matrix(ctx: Ctx, a: SymbolsArgs) -> ToolOutput:
    cols = {s.upper(): _returns(ctx, s) for s in a.symbols}
    if len(cols) < 2:
        raise ValueError("Need at least two symbols for a correlation matrix.")
    corr = pd.DataFrame(cols).dropna().corr()
    return ToolOutput({"correlation": corr.round(3).to_dict()}, series={"correlation": corr},
                      tables={"correlation": corr.round(3).to_dict()})


def portfolio_risk(ctx: Ctx, a: PortfolioArgs) -> ToolOutput:
    """Value-weighted risk of the user's declared holdings (needs price data for them)."""
    qs = _qs()
    values = {}
    for h in ctx.holdings:
        sym = str(h["symbol"]).upper()
        if sym in ctx.frames and h.get("quantity"):
            values[sym] = float(h["quantity"]) * float(ctx.frames[sym]["Close"].dropna().iloc[-1])
    if not values:
        raise ValueError("No declared holdings with fetched price data.")
    total = sum(values.values())
    weights = {s: v / total for s, v in values.items()}
    rets = pd.DataFrame({s: _returns(ctx, s) for s in weights}).dropna()
    port = sum(rets[s] * w for s, w in weights.items())
    alloc = {s: _f(w) for s, w in weights.items()}
    summary = {
        "allocation": alloc, "total_value_priced": _f(total, 2),
        "annual_volatility": _f(qs.volatility(port, periods=ctx.periods)),
        "sharpe": _f(qs.sharpe(port, rf=0.0, periods=ctx.periods), 3),
        "sortino": _f(qs.sortino(port, rf=0.0, periods=ctx.periods), 3),
        "max_drawdown": _f(qs.max_drawdown(port)),
        "value_at_risk_95": _f(qs.value_at_risk(port, sigma=1, confidence=0.95)),
        "largest_position": max(alloc, key=lambda k: alloc[k] or 0),
    }
    return ToolOutput(summary, series={"portfolio_cumulative": ((1 + port).cumprod() - 1).to_frame("portfolio")},
                      tables={"allocation": alloc, "portfolio_risk": summary})


# ----------------------------------------------------------------- registry
@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("performance_summary", "Total return, CAGR, volatility, best/worst period and cumulative-return series for one or more symbols.", SymbolsArgs, performance_summary),
    Tool("sharpe_ratio", "Annualised Sharpe ratio for one symbol.", SharpeArgs, sharpe_ratio),
    Tool("sortino_ratio", "Annualised Sortino ratio for one symbol.", SharpeArgs, sortino_ratio),
    Tool("max_drawdown", "Maximum and current drawdown for one symbol, plus drawdown series.", SymbolArgs, max_drawdown),
    Tool("value_at_risk", "Value at Risk for one symbol at a confidence level.", VarArgs, value_at_risk),
    Tool("technical_indicators", "RSI, MACD, Bollinger Bands, SMA, EMA for one symbol (also produces overlay series for charts).", IndicatorArgs, technical_indicators),
    Tool("correlation_matrix", "Return correlation matrix across two or more symbols.", SymbolsArgs, correlation_matrix),
    Tool("portfolio_risk", "Allocation weights and risk metrics (vol, Sharpe, Sortino, drawdown, VaR) of the user's declared holdings.", PortfolioArgs, portfolio_risk),
]}


def groq_tool_specs() -> list[dict]:
    specs = []
    for t in TOOLS.values():
        schema = t.args.model_json_schema()
        schema.pop("title", None)
        specs.append({"type": "function", "function": {"name": t.name, "description": t.description, "parameters": schema}})
    return specs


def run_tool(name: str, raw_args: dict, ctx: Ctx) -> ToolOutput:
    tool = TOOLS.get(name)
    if not tool:
        raise ValueError(f"Unknown tool {name}")
    args = tool.args(**raw_args)       # pydantic validation = schema enforcement
    return tool.fn(ctx, args)
