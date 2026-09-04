"""Read side of the market data: the CSV snapshot written by services/market_api.py.

Public API:
    load_closes_full()      close prices, keeping NaN for the dynamic universe
    get_real_adtv(tickers)  {ticker: adtv_bn} over the last 60 sessions, or up to `as_of`
    get_liquidity_profile() per-ticker liquidity, percentiles and price impact
    data_coverage()         first and last date of the price panel

`as_of` freezes ADTV and liquidity at a past date instead of the end of the file. It is
required whenever a backtest has an `end_date`, or liquidity would look ahead.

Everything is cached at module level; the snapshot does not change within a session.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from app import paths
from app.data.universe_config import TICKERS_FTSE

logger = logging.getLogger(__name__)

# app/paths.py decides the location (DATA_DIR overrides it in a container)
CSV_DATA_DIR: Path = paths.DATA_DIR

# Module-level cache, loaded once per process
_adtv_cache: dict[str, float] | None = None
_liq_profile_cache: dict[tuple[int, str | None], dict[str, dict]] = {}  # {(window, as_of): ...}


# Loaders

_closes_full_cache: dict[tuple[str, ...], pd.DataFrame] = {}


def load_closes_full(tickers: list[str], start: str = "2020-01-02") -> pd.DataFrame:
    """Close prices for `tickers`, keeping NaN where a ticker is not listed yet.

    The frame is NOT reduced to dates common to every ticker; the dynamic universe
    depends on those NaNs, which the engine masks. The calendar is the union of trading
    days from `start` on.
    """
    key = (tuple(tickers), start)
    if key in _closes_full_cache:
        return _closes_full_cache[key]

    frames: list[pd.Series] = []
    for ticker in tickers:
        csv_path = CSV_DATA_DIR / f"{ticker}.csv"
        if not csv_path.exists():
            logger.warning(f"CSV không tìm thấy: {csv_path}")
            continue
        df = pd.read_csv(csv_path, parse_dates=["time"])
        df = df.drop_duplicates(subset="time", keep="last")
        frames.append(df.set_index("time")["close"].rename(ticker))

    closes = pd.concat(frames, axis=1).sort_index()
    closes = closes[~closes.index.duplicated(keep="last")]
    closes = closes.dropna(how="all")                  # drop days where no ticker has data
    closes = closes[closes.index >= pd.Timestamp(start)]
    closes = closes.reindex(columns=tickers)           # keep the column order
    closes.index.name = "date"
    _closes_full_cache[key] = closes
    if len(closes):
        logger.info(
            f"CSV full loaded: {len(closes)} ngày, {len(closes.columns)} tickers, "
            f"{closes.index[0].date()} → {closes.index[-1].date()} (giữ NaN)"
        )
    else:
        # start beyond the last date gives an empty frame; runner._load_market reports it
        logger.warning(f"CSV full loaded: 0 ngày (start={start} sau vùng dữ liệu)")
    return closes


# ADTV

def get_real_adtv(tickers: list[str] | None = None, days: int = 60,
                  as_of: str | None = None) -> dict[str, float]:
    """Average daily turnover in billions VND over the last `days` sessions.

    adtv = mean(close * volume) / 1e9

    Args:
        tickers: tickers to compute, default all of TICKERS_FTSE
        days:    number of recent sessions, default 60
        as_of:   cut the window at this date; required when a backtest has an end_date

    Returns {ticker: adtv_bn}.
    """
    global _adtv_cache
    if _adtv_cache is not None and tickers is None and as_of is None:
        return _adtv_cache

    target = tickers or TICKERS_FTSE
    cutoff = pd.Timestamp(as_of) if as_of else None
    result: dict[str, float] = {}

    for ticker in target:
        if ticker not in TICKERS_FTSE:
            continue
        csv_path = CSV_DATA_DIR / f"{ticker}.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path, parse_dates=["time"])
            df = df.drop_duplicates(subset="time", keep="last").sort_values("time")
            if cutoff is not None:
                df = df[df["time"] <= cutoff]
            recent = df.tail(days)
            if len(recent) == 0:
                continue
            # close (VND) * volume (shares) / 1e9 = billions VND
            adtv = float((recent["close"] * recent["volume"]).mean() / 1e9)
            result[ticker] = round(adtv, 2)
        except Exception as e:
            logger.warning(f"Không tính được ADTV cho {ticker}: {e}")

    if tickers is None and as_of is None:
        _adtv_cache = result

    return result


# Liquidity profile over a recent window (percentiles + price impact)

_CRASH_RET = -0.03          # shock day: down 3% or more
_DEFAULT_CRASH_MULT = 2.5   # fallback when there are too few shock days


def get_liquidity_profile(tickers: list[str] | None = None,
                          window: int = 252,
                          as_of: str | None = None) -> dict[str, dict]:
    """Liquidity profile per ticker over that ticker's own last `window` sessions.

    Deliberately not the full history, which would mismeasure recent listings and
    regime changes. `as_of` moves the window back for a backtest with an end_date.

    Per ticker: liq_mean20 (last 20 sessions, billions per session, used for capacity and
    slippage), liq_p50 / liq_p25 / liq_mean over the window, sigma (std of daily return),
    amihud_normal (median |ret| / turnover on normal days), crash_impact_mult (shock-day
    impact divided by normal), n_days and short_history.
    """
    cache_key = (window, as_of)
    if cache_key in _liq_profile_cache and tickers is None:
        return _liq_profile_cache[cache_key]

    target = tickers or TICKERS_FTSE
    cutoff = pd.Timestamp(as_of) if as_of else None
    out: dict[str, dict] = {}

    for t in target:
        if t not in TICKERS_FTSE:
            continue
        csv_path = CSV_DATA_DIR / f"{t}.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path, parse_dates=["time"])
            df = df.drop_duplicates(subset="time", keep="last").sort_values("time")
            if cutoff is not None:
                df = df[df["time"] <= cutoff]
            df = df.tail(window)
            if len(df) < 2:
                continue
            turnover = (df["close"] * df["volume"] / 1e9).astype(float)   # billions VND per session
            ret = df["close"].pct_change()
            amihud = (ret.abs() / turnover.replace(0.0, np.nan))          # impact per billion
            crash_mask = ret <= _CRASH_RET
            am_normal = float(amihud[~crash_mask].median())
            am_crash = float(amihud[crash_mask].median()) if crash_mask.sum() >= 5 else np.nan
            if am_normal and am_normal > 0 and not np.isnan(am_crash):
                crash_mult = round(am_crash / am_normal, 2)
            else:
                crash_mult = _DEFAULT_CRASH_MULT

            out[t] = {
                "liq_mean20": round(float(turnover.tail(20).mean()), 3),  # average of the last 20 sessions
                "liq_p50": round(float(turnover.median()), 3),
                "liq_p25": round(float(turnover.quantile(0.25)), 3),
                "liq_mean": round(float(turnover.mean()), 3),
                "sigma": round(float(ret.std()), 5),
                "amihud_normal": round(am_normal, 6) if am_normal and am_normal > 0 else 0.0,
                "crash_impact_mult": crash_mult,
                "n_days": int(len(df)),
                "short_history": len(df) < window,
            }
        except Exception as e:
            logger.warning(f"liquidity profile lỗi cho {t}: {e}")

    if tickers is None:
        _liq_profile_cache[cache_key] = out
    return out


# Data coverage, used for the date bounds in the UI

def data_coverage() -> tuple[str | None, str | None]:
    """First and last date of the price panel as 'YYYY-MM-DD'.

    Used by /config/defaults for the date bounds in the UI. Returns (None, None) when the
    snapshot is still empty, i.e. a fresh install where the sync job never ran.
    """
    try:
        closes = load_closes_full(list(TICKERS_FTSE), start="1900-01-01")
    except ValueError:                            # no CSV could be read
        return (None, None)
    if closes.empty:
        return (None, None)
    return (closes.index[0].strftime("%Y-%m-%d"),
            closes.index[-1].strftime("%Y-%m-%d"))


def clear_cache() -> None:
    """Clear every cache; used by tests and after the snapshot changes."""
    global _adtv_cache, _liq_profile_cache, _closes_full_cache
    _closes_full_cache = {}
    _adtv_cache = None
    _liq_profile_cache = {}
    logger.info("csv_data cache cleared")
