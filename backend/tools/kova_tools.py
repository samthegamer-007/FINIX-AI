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
    full_frames: dict | None = None          # untrimmed history (used by price_simulation when a short window was requested)
    news: list | None = None                 # Rome's raw news articles (used by news_sentiment)


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
    if len(r) < 5:
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


class SimArgs(SymbolArgs):
    horizon_days: int = Field(10, ge=1, le=60, description="Trading days ahead (about calendar days x 5/7)")
    model: Literal["garch", "gbm", "bootstrap"] = Field(
        "garch", description="garch = GARCH(1,1) Student-t Monte Carlo (volatility clustering); gbm = geometric Brownian motion; bootstrap = resample history")


class NoArgs(BaseModel):
    pass


# ----------------------------------------------------------------- tools
def performance_summary(ctx: Ctx, a: SymbolsArgs) -> ToolOutput:
    qs = _qs()
    unit = {252: "day", 52: "week", 12: "month"}.get(ctx.periods, "period")
    rows, cum = {}, {}
    for s in a.symbols:
        r = _returns(ctx, s)
        rows[s.upper()] = {
            "total_return": _f((1 + r).prod() - 1),
            "cagr": _f(qs.cagr(r, periods=ctx.periods)),
            "annual_volatility": _f(qs.volatility(r, periods=ctx.periods)),
            f"best_single_{unit}_return": _f(r.max()), f"worst_single_{unit}_return": _f(r.min()),
            "data_frequency": unit,
            "periods_used": int(len(r)),
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
    n = len(close)
    need = {"rsi": 16, "macd": 36, "bbands": 21, "sma": 21, "ema": 21}
    skipped = [i for i in a.indicators if n < need.get(i, 0)]
    for ind in a.indicators:
        if n < need.get(ind, 0):
            continue
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
            out["SMA_20"] = ta.sma(close, 20)
            latest["sma_20"] = _f(out["SMA_20"].iloc[-1], 2)
            if n >= 50:
                out["SMA_50"] = ta.sma(close, 50)
                latest["sma_50"] = _f(out["SMA_50"].iloc[-1], 2)
        elif ind == "ema":
            out["EMA_20"] = ta.ema(close, 20)
            latest["ema_20"] = _f(out["EMA_20"].iloc[-1], 2)
    latest["last_close"] = _f(close.iloc[-1], 2)
    if skipped:
        latest["not_enough_history_for"] = skipped
    if out.shape[1] == 0:
        raise ValueError(f"only {n} price rows - too short for the requested indicators")
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


def return_distribution(ctx: Ctx, a: SymbolArgs) -> ToolOutput:
    r = _returns(ctx, a.symbol)
    unit = {252: "day", 52: "week", 12: "month"}.get(ctx.periods, "period")
    return ToolOutput(
        {"symbol": a.symbol.upper(), "data_frequency": unit, "mean_return": _f(r.mean(), 5), "std_dev": _f(r.std(), 5),
         "skewness": _f(r.skew(), 3), "excess_kurtosis": _f(r.kurt(), 3), "share_of_positive_periods": _f((r > 0).mean(), 3)},
        series={f"returns_{a.symbol.upper()}": r.to_frame("returns")})


def monthly_returns(ctx: Ctx, a: SymbolArgs) -> ToolOutput:
    close = _close(ctx, a.symbol)
    m = close.resample("ME").last().pct_change().dropna()
    if len(m) < 3:
        raise ValueError("Need at least 3 months of data for a monthly returns table.")
    tbl = pd.DataFrame({"y": m.index.year, "m": m.index.month, "v": m.values}).pivot(index="y", columns="m", values="v")
    names = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
    tbl.columns = [names[c] for c in tbl.columns]
    tbl.index = [str(i) for i in tbl.index]
    best, worst = m.idxmax(), m.idxmin()
    return ToolOutput({"symbol": a.symbol.upper(), "months_covered": int(len(m)),
                       "best_month": f"{best:%Y-%m} ({m.max():.1%})", "worst_month": f"{worst:%Y-%m} ({m.min():.1%})",
                       "share_of_positive_months": _f((m > 0).mean(), 3)},
                      series={f"monthly_{a.symbol.upper()}": tbl})


FIN_LEXICON = {   # finance terms the general-purpose VADER lexicon scores poorly (standard practice: extend the lexicon)
    "beat": 1.8, "beats": 1.8, "surge": 2.2, "surges": 2.2, "soar": 2.4, "soars": 2.4, "rally": 2.0, "rallies": 2.0,
    "upgrade": 2.0, "upgraded": 2.0, "outperform": 1.9, "record": 1.2, "bullish": 2.2, "rebound": 1.6, "gains": 1.5,
    "miss": -1.8, "misses": -1.8, "plunge": -2.5, "plunges": -2.5, "slump": -2.1, "selloff": -2.2, "sell-off": -2.2,
    "downgrade": -2.0, "downgraded": -2.0, "underperform": -1.9, "bearish": -2.2, "default": -2.4, "bankruptcy": -3.0,
    "probe": -1.5, "lawsuit": -1.6, "fraud": -3.0, "layoffs": -1.7, "warning": -1.6, "slowdown": -1.6, "recession": -2.2,
    "tariff": -1.2, "tariffs": -1.2, "volatile": -0.8, "muted": -0.8, "lagging": -1.2, "selling": -0.9, "inflows": 1.2,
    "outflows": -1.2, "weak": -1.4, "weakness": -1.4, "strong": 1.4, "strength": 1.3,
}


def _simulate(close: pd.Series, h: int, model: str, n: int = 3000):
    """Returns (cumulative-return paths [n x h] as fractions, info dict). Industry-standard models:
    GARCH(1,1) with Student-t errors (arch), geometric Brownian motion, historical bootstrap."""
    rng = np.random.default_rng(42)                       # fixed seed: same data -> same answer
    pct = close.pct_change().dropna().tail(500)
    logr = np.log(close / close.shift(1)).dropna().tail(500)
    info = {"model": model}
    if model == "garch":
        if len(logr) < 120:
            info.update(model="gbm", model_fallback="GARCH needs about 120 daily returns; used GBM instead")
            model = "gbm"
        else:
            try:
                import warnings
                from arch import arch_model
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    from arch.univariate import StudentsT
                    am = arch_model(logr.values * 100, mean="Constant", vol="GARCH", p=1, q=1, dist="t")
                    am.distribution = StudentsT(seed=np.random.RandomState(42))      # reproducible simulation
                    res = am.fit(disp="off")
                    if res.convergence_flag != 0:
                        raise RuntimeError("GARCH did not converge")
                    f = res.forecast(horizon=h, method="simulation", simulations=n, reindex=False)
                sims = f.simulations.values[-1] / 100.0      # [n x h] daily log returns
                paths = np.exp(np.cumsum(sims, axis=1)) - 1
                pr = res.params
                persistence = float(pr.get("alpha[1]", 0) + pr.get("beta[1]", 0))
                info.update(garch_persistence=_f(persistence, 3),
                            current_annual_vol=_f(float(res.conditional_volatility[-1]) / 100 * np.sqrt(252), 4),
                            forecast_annual_vol=_f(float(np.sqrt(f.variance.values[-1].mean())) / 100 * np.sqrt(252), 4),
                            student_t_dof=_f(pr.get("nu"), 2))
                del res, f
                return paths, info
            except Exception as exc:                       # missing/oversized library, no convergence, low memory
                info.update(model="gbm", model_fallback=f"GARCH unavailable ({str(exc)[:60]}); used GBM instead")
                model = "gbm"
    if model == "bootstrap":
        if len(pct) < 20:
            raise ValueError(f"Need at least 20 historical returns ({len(pct)} available).")
        paths = np.cumprod(1 + rng.choice(pct.values, size=(n, h), replace=True), axis=1) - 1
        info["history_returns_used"] = int(len(pct))
        return paths, info
    if len(logr) < 20:
        raise ValueError(f"Need at least 20 historical returns ({len(logr)} available).")
    mu, sigma = float(logr.mean()), float(logr.std(ddof=1))
    z = rng.standard_normal((n, h))
    paths = np.exp(np.cumsum((mu - 0.5 * sigma ** 2) + sigma * z, axis=1)) - 1
    info.update(history_returns_used=int(len(logr)), annual_vol_used=_f(sigma * np.sqrt(252), 4))
    return paths, info


def price_simulation(ctx: Ctx, a: SimArgs) -> ToolOutput:
    """Monte Carlo price simulation. Output is a scenario RANGE from a statistical model, not a forecast."""
    sym = a.symbol.upper()
    frames = ctx.full_frames if (ctx.full_frames and sym in ctx.full_frames) else ctx.frames
    if sym not in frames:
        raise ValueError(f"No data for {a.symbol}")
    close = frames[sym]["Close"].dropna()
    h = int(a.horizon_days)
    paths, info = _simulate(close, h, a.model)
    term = paths[:, -1]
    last = float(close.iloc[-1])
    q = dict(zip(("p5", "p25", "p50", "p75", "p95"), np.percentile(term, [5, 25, 50, 75, 95])))
    tail = np.sort(term)[: max(1, int(len(term) * 0.05))]
    summary = {"symbol": sym, "model": info.pop("model"), "horizon_trading_days": h, "simulations": int(len(term)),
               "last_close": _f(last, 2),
               **{f"return_{k}": _f(v) for k, v in q.items()},
               **{f"price_{k}": _f(last * (1 + v), 2) for k, v in q.items()},
               "probability_of_loss": _f((term < 0).mean(), 3),
               "var_95_horizon": _f(np.percentile(term, 5)), "expected_shortfall_95": _f(tail.mean()),
               **info, "note": "Scenario range from a statistical model; not a forecast or a guarantee."}
    # fan-chart frame: recent closes + percentile bands per future trading day
    hist = close.tail(40)
    fut_idx = pd.bdate_range(hist.index[-1] + pd.Timedelta(days=1), periods=h)
    bands = {k: last * (1 + np.percentile(paths, pc, axis=0)) for k, pc in
             (("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95))}
    fan = pd.concat([pd.DataFrame({"close": hist.values}, index=hist.index),
                     pd.DataFrame(bands, index=fut_idx)])
    for k in bands:
        fan.loc[hist.index[-1], k] = last                  # bands start at the last close
    return ToolOutput(summary, series={f"fan_{sym}_{summary['model']}": fan})


def news_sentiment(ctx: Ctx, a: NoArgs) -> ToolOutput:
    """Headline/description sentiment with VADER (lexicon extended with finance terms). Transparent, no LLM."""
    arts = [x for x in (ctx.news or []) if (x.get("title") or x.get("description"))]
    if not arts:
        raise ValueError("no news articles to score")
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    sia.lexicon.update(FIN_LEXICON)
    scored = []
    for x in arts[:20]:
        txt = f"{x.get('title') or ''}. {x.get('description') or ''}"
        scored.append((sia.polarity_scores(txt)["compound"], (x.get("title") or "")[:110]))
    vals = np.array([v for v, _ in scored])
    mean = float(vals.mean())
    scored.sort()
    label = "positive-leaning" if mean >= 0.15 else "negative-leaning" if mean <= -0.15 else "mixed/neutral"
    return ToolOutput({"articles_scored": int(len(vals)), "mean_compound": _f(mean, 3), "label": label,
                       "share_positive": _f((vals > 0.05).mean(), 2), "share_negative": _f((vals < -0.05).mean(), 2),
                       "most_negative_headline": scored[0][1], "most_positive_headline": scored[-1][1],
                       "note": "VADER lexicon sentiment (finance terms added); a rough gauge, not a trading signal."})


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
    Tool("return_distribution", "Distribution statistics of periodic returns for one symbol (feeds a histogram).", SymbolArgs, return_distribution),
    Tool("monthly_returns", "Calendar month-by-month return table for one symbol (feeds a heatmap).", SymbolArgs, monthly_returns),
    Tool("correlation_matrix", "Return correlation matrix across two or more symbols.", SymbolsArgs, correlation_matrix),
    Tool("price_simulation", "Monte Carlo simulation of a symbol's price over the next N trading days (GARCH(1,1) Student-t, GBM or bootstrap): percentile return/price range, probability of loss, VaR and expected shortfall, plus a fan-chart series. Use when the user asks for predictions, outlook or the next N days.", SimArgs, price_simulation),
    Tool("news_sentiment", "Score the fetched news headlines with a finance-extended VADER lexicon (mean sentiment, share positive/negative). Use for outlook/sentiment questions.", NoArgs, news_sentiment),
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
