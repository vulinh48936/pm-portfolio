"""FTSE GEIS benchmark (time-varying weights) and the frob_z regime signal."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app import paths
from app.data.universe_config import TICKERS_FTSE

# Data locations come from app/paths.py (DATA_DIR / WEIGHT_JSON override them)
_WEIGHT_JSON = paths.WEIGHT_JSON
_INDEX_FTSE_CSV = paths.INDEX_FTSE_CSV
_INDEX_VNINDEX_CSV = paths.INDEX_VNINDEX_CSV

_periods_cache: list[dict] | None = None


def _load_periods() -> list[dict]:
    global _periods_cache
    if _periods_cache is None:
        _periods_cache = json.loads(_WEIGHT_JSON.read_text(encoding="utf-8"))["periods"]
    return _periods_cache


def build_time_varying_weights(calendar: pd.DatetimeIndex,
                               tickers: list[str] = TICKERS_FTSE,
                               periods_raw: list[dict] | None = None,
                               avail: np.ndarray | None = None) -> np.ndarray:
    """(T, N) FTSE TARGET weights, the walk-forward anchor; these do not drift.

    Each row holds the weights of the period effective that day, masked by availability
    and renormalized to 1. Duplicate effective_dates keep the last entry in the file.
    Days before the first period are backfilled with that first period. Tickers not
    listed yet, or absent from the period, get weight 0.
    """
    if periods_raw is None:
        periods_raw = _load_periods()

    seen: dict[str, dict] = {p["effective_date"]: p for p in periods_raw}
    effective_periods = sorted(seen.values(), key=lambda p: p["effective_date"])

    def parse_raw(period: dict) -> np.ndarray:
        raw: dict[str, float] = {}
        for c in period["constituents"]:
            t = c["ticker"].replace(" ◆", "").strip()
            raw[t] = c["weight_pct"] / 100.0
        return np.array([raw.get(t, 0.0) for t in tickers])

    parsed = {p["effective_date"]: parse_raw(p) for p in effective_periods}
    eff_dates = sorted(parsed.keys())

    T, N = len(calendar), len(tickers)
    weights = np.zeros((T, N))
    for i, date in enumerate(calendar):
        date_str = date.strftime("%Y-%m-%d")
        valid = [d for d in eff_dates if d <= date_str]
        row = parsed[valid[-1] if valid else eff_dates[0]].copy()
        if avail is not None:
            row = row * avail[i]            # not listed yet -> 0
        s = row.sum()
        weights[i] = row / s if s > 0 else row
    return weights


def load_ftse_drift_ret(calendar: pd.DatetimeIndex) -> np.ndarray:
    """Daily benchmark return: index_ret from index_ftse.csv, the drift series.

    This is the benchmark performance is measured against: buy-and-hold between review
    dates, aligned to the calendar with missing days as 0.
    """
    df = pd.read_csv(_INDEX_FTSE_CSV, parse_dates=["date"]).set_index("date")
    return df["index_ret"].reindex(calendar).fillna(0.0).values


def ftse_index_range() -> tuple[str | None, str | None]:
    """First and last date in index_ftse.csv: the real benchmark range.

    Before the first date load_ftse_drift_ret() fills zeros, so the benchmark would look
    flat instead of failing. That makes this the valid floor for start_date, even though
    price history reaches further back.
    """
    if not _INDEX_FTSE_CSV.exists():
        return (None, None)                      # fresh install, job never ran
    df = pd.read_csv(_INDEX_FTSE_CSV, parse_dates=["date"])
    if df.empty:
        return (None, None)
    return (df["date"].min().strftime("%Y-%m-%d"),
            df["date"].max().strftime("%Y-%m-%d"))


def load_vnindex_ret(calendar: pd.DatetimeIndex) -> np.ndarray:
    """VNINDEX daily return, the second reference line, aligned to the calendar.

    Uses the same anchor as bench_ret, so Strategy, FTSE and VNINDEX all start at 100.
    """
    df = pd.read_csv(_INDEX_VNINDEX_CSV, parse_dates=["date"]).set_index("date")
    return df["vnindex_ret"].reindex(calendar).fillna(0.0).values


def load_ftse_drift_weights(calendar: pd.DatetimeIndex,
                            tickers: list[str]) -> np.ndarray:
    """(T, N) DRIFTED FTSE weights (the _w columns), i.e. what the index actually holds.

    The weight grid and attribution compare drifted against drifted; mid-period the
    static target can differ a lot from what is held.
    """
    df = pd.read_csv(_INDEX_FTSE_CSV, parse_dates=["date"]).set_index("date")
    out = np.zeros((len(calendar), len(tickers)))
    for i, t in enumerate(tickers):
        col = f"{t}_w"
        if col in df.columns:
            out[:, i] = df[col].reindex(calendar, method="ffill").fillna(0.0).values
    return out


def compute_frob_z_series(closes_arr: np.ndarray,
                          calendar: pd.DatetimeIndex) -> pd.Series:
    """Expanding z-score of the Frobenius norm of correlation change (no look-ahead).

    A regime-shift signal for rebalance triggers: 30-day vs 90-day correlation,
    min_periods=60 so an early near-zero std cannot produce outliers.
    """
    short_w, long_w = 30, 90
    rets = np.diff(closes_arr, axis=0) / closes_arr[:-1]
    T = len(rets)
    frob_raw = []
    for end in range(long_w, T):
        cs = np.corrcoef(rets[end - short_w: end].T)
        cl = np.corrcoef(rets[max(0, end - long_w): end].T)
        frob_raw.append(float(np.sqrt(((cs - cl) ** 2).sum())))
    fs = pd.Series(frob_raw)
    exp_mean = fs.expanding(min_periods=60).mean().shift(1)
    exp_std = fs.expanding(min_periods=60).std().shift(1)
    z = (fs - exp_mean) / (exp_std + 1e-8)
    z_dates = calendar[long_w + 1: long_w + 1 + len(frob_raw)]
    return pd.Series(z.fillna(0.0).values, index=z_dates)
