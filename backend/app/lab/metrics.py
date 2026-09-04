"""Metrics for building a base portfolio: tracking error against the benchmark,
information ratio, active share and concentration.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from app.data.universe_config import TICKER_META


def _max_drawdown(cumret: np.ndarray) -> float:
    peak = np.maximum.accumulate(cumret)
    return float(((cumret - peak) / peak).min())


def _sector_hhi(w: np.ndarray, tickers: list[str]) -> float:
    """Sector Herfindahl index from average weights; 0-1, higher means concentrated."""
    acc: dict[str, float] = defaultdict(float)
    for i, t in enumerate(tickers):
        sec = TICKER_META.get(t, {}).get("sector", "Khác")
        acc[sec] += float(w[i])
    return float(sum(v ** 2 for v in acc.values()))


def compute_metrics(port_ret: np.ndarray, bench_ret: np.ndarray,
                    w_tv: np.ndarray, w_bench_tv: np.ndarray,
                    turnover_log: pd.DataFrame, tickers: list[str]) -> dict:
    """Metrics from the return series and time-varying weights.

    port_ret and bench_ret are (T,) daily returns; row 0 is dropped.
    """
    r = port_ret[1:]
    b = bench_ret[1:]
    cum = np.cumprod(1.0 + r)
    cum_b = np.cumprod(1.0 + b)
    ann_factor = 252.0 / len(r)

    ann_ret = float(cum[-1] ** ann_factor - 1.0)
    ann_vol = float(np.std(r) * np.sqrt(252.0))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    maxdd = _max_drawdown(cum)
    calmar = ann_ret / abs(maxdd) if maxdd < 0 else 0.0

    downside = r[r < 0]
    dd_dev = float(np.std(downside) * np.sqrt(252.0)) if len(downside) else 0.0
    sortino = ann_ret / dd_dev if dd_dev > 0 else 0.0

    # versus benchmark
    active = r - b
    te = float(np.std(active) * np.sqrt(252.0))
    ann_alpha = ann_ret - float(cum_b[-1] ** ann_factor - 1.0)
    ir = ann_alpha / te if te > 0 else 0.0

    # capture ratios
    up = b > 0
    down = b < 0
    up_cap = (float(r[up].mean() / b[up].mean()) if up.any() and b[up].mean() != 0 else 0.0)
    down_cap = (float(r[down].mean() / b[down].mean()) if down.any() and b[down].mean() != 0 else 0.0)

    # worst rolling underperformance over ~63 (3M) and 126 (6M) sessions
    excess = np.cumprod(1 + r) - np.cumprod(1 + b)
    def _worst_roll(win: int) -> float:
        if len(excess) <= win:
            return float(excess.min())
        diff = excess[win:] - excess[:-win]
        return float(min(diff.min(), 0.0))

    # weight-based (time-averaged)
    active_share = float(0.5 * np.abs(w_tv - w_bench_tv).sum(axis=1).mean())
    avg_w = w_tv.mean(axis=0)
    max_weight = float(w_tv.max())
    top3 = float(np.sort(avg_w)[::-1][:3].sum())
    hhi_sector = _sector_hhi(avg_w, tickers)

    n_years = len(r) / 252.0
    total_to = float(turnover_log["turnover"].sum()) if len(turnover_log) else 0.0
    n_rebal = int(turnover_log["rebalanced"].sum()) if "rebalanced" in turnover_log else len(turnover_log)

    return {
        "final": round(float(cum[-1] * 100), 1),
        "ann_ret_pct": round(ann_ret * 100, 2),
        "ann_vol_pct": round(ann_vol * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "maxdd_pct": round(maxdd * 100, 1),
        "calmar": round(calmar, 2),
        "te_vs_bench_pct": round(te * 100, 2),
        "ann_alpha_pct": round(ann_alpha * 100, 2),
        "information_ratio": round(ir, 2),
        "active_share_pct": round(active_share * 100, 1),
        "up_capture": round(up_cap, 2),
        "down_capture": round(down_cap, 2),
        "worst_roll_3m_pp": round(_worst_roll(63) * 100, 1),
        "worst_roll_6m_pp": round(_worst_roll(126) * 100, 1),
        "max_weight_pct": round(max_weight * 100, 1),
        "top3_weight_pct": round(top3 * 100, 1),
        "sector_hhi": round(hhi_sector, 3),
        "ann_turnover_pct": round(total_to / n_years * 100, 1) if n_years else 0.0,
        "n_rebal": n_rebal,
    }


def index_metrics(port_ret: np.ndarray, bench_ret: np.ndarray) -> dict:
    """Return-based metrics for a reference index (FTSE or VNINDEX).

    Weight-based metrics are '-' because an index is not a book we hold. TE and alpha
    are measured against `bench_ret`, so FTSE against itself gives zero.
    """
    r = port_ret[1:]
    b = bench_ret[1:]
    cum = np.cumprod(1.0 + r)
    cum_b = np.cumprod(1.0 + b)
    ann_factor = 252.0 / len(r)

    ann_ret = float(cum[-1] ** ann_factor - 1.0)
    ann_vol = float(np.std(r) * np.sqrt(252.0))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    maxdd = _max_drawdown(cum)
    calmar = ann_ret / abs(maxdd) if maxdd < 0 else 0.0

    downside = r[r < 0]
    dd_dev = float(np.std(downside) * np.sqrt(252.0)) if len(downside) else 0.0
    sortino = ann_ret / dd_dev if dd_dev > 0 else 0.0

    active = r - b
    te = float(np.std(active) * np.sqrt(252.0))
    ann_alpha = ann_ret - float(cum_b[-1] ** ann_factor - 1.0)
    ir = ann_alpha / te if te > 0 else 0.0

    up = b > 0
    down = b < 0
    up_cap = (float(r[up].mean() / b[up].mean()) if up.any() and b[up].mean() != 0 else 0.0)
    down_cap = (float(r[down].mean() / b[down].mean()) if down.any() and b[down].mean() != 0 else 0.0)

    excess = np.cumprod(1 + r) - np.cumprod(1 + b)
    def _worst_roll(win: int) -> float:
        if len(excess) <= win:
            return float(excess.min())
        diff = excess[win:] - excess[:-win]
        return float(min(diff.min(), 0.0))

    return {
        "final": round(float(cum[-1] * 100), 1),
        "ann_ret_pct": round(ann_ret * 100, 2),
        "ann_vol_pct": round(ann_vol * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "maxdd_pct": round(maxdd * 100, 1),
        "calmar": round(calmar, 2),
        "te_vs_bench_pct": round(te * 100, 2),
        "ann_alpha_pct": round(ann_alpha * 100, 2),
        "information_ratio": round(ir, 2),
        "up_capture": round(up_cap, 2),
        "down_capture": round(down_cap, 2),
        "worst_roll_3m_pp": round(_worst_roll(63) * 100, 1),
        "worst_roll_6m_pp": round(_worst_roll(126) * 100, 1),
        # weight-based, not meaningful for an index
        "active_share_pct": "—",
        "max_weight_pct": "—",
        "top3_weight_pct": "—",
        "sector_hhi": "—",
        "ann_turnover_pct": "—",
        "n_rebal": "—",
    }
