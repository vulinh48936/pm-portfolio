"""Minimum AUM at which round-lot buying still tracks the target weights.

Implementation TE: sqrt((w_lot - w_target)' S (w_lot - w_target)), where w_lot is what
you actually hold after buying whole 100-share lots at that AUM, including uninvested
cash. It tends to 0 as AUM grows. This is not TE against the benchmark, which would be
meaningless for a deliberately active strategy.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


# AUM ladder (billions VND) for the implementation-TE curve, 20 million to 1 billion.
AUM_TIERS_BN: list[float] = [
    0.02, 0.035, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0,
]


def min_aum(weights: dict[str, float], tol: float = 0.05,
            rec_tol: float = 0.02, aum_tiers: list[float] | None = None,
            current_aum_bn: float | None = None,
            weights_history: list[dict[str, float]] | None = None,
            dates: list[Any] | None = None,
            cov_window: int | None = 252,
            as_of: str | None = None) -> dict[str, Any]:
    """Smallest AUM (billions) where implementation TE stays under `tol`, and under
    `rec_tol` for the recommended figure.

      - `weights_history` + `dates`: compute lot TE per session with that session's own
        weights and prices, then take the median, so one odd last day cannot dominate.
        Without them only `weights` at the latest prices is used.
      - `cov_window`: covariance over the most recent sessions only (252 by default),
        so it reflects the current regime. None uses the whole history.
      - `as_of`: freeze prices at the backtest end date, so "recent" means recent
        relative to that window rather than to today.

    Also returns `te_curve` over the AUM ladder, on the same basis as the two figures
    above, so both sit on the curve.
    """
    from app.services.csv_data import load_closes_full
    from app.lib.allocator import compute_lot_positions, LOT_SIZE

    days = weights_history if weights_history else [weights]
    universe = sorted({t for wd in days for t, w in wd.items() if w > 0})
    empty = {"min_aum_bn": 0.0, "recommended_aum_bn": 0.0,
             "bottleneck_ticker": None, "bottleneck_weight_pct": 0.0,
             "te_curve": []}
    if not universe:
        return empty

    # Prices and covariance over exactly the held universe
    closes = load_closes_full(universe)
    if as_of:
        closes = closes[closes.index <= pd.Timestamp(as_of)]
        if len(closes) < 2:
            return empty

    # Annualized covariance over the recent window; names without full data in that
    # window (a very recent IPO) are dropped from the covariance and the TE.
    win = closes[universe].tail((cov_window + 1) if cov_window else len(closes))
    rets_win = win.pct_change(fill_method=None).iloc[1:]   # no padding: a missing session must show up as NaN
    valid = [t for t in universe if bool(rets_win[t].notna().all())]
    if not valid:
        return empty
    cov = (rets_win[valid].cov() * 252.0).values

    # Prices per session, forward-filled for gaps; without dates, only the latest row
    day_dates = dates if (weights_history and dates) else [closes.index[-1]]
    price_rows = closes[valid].reindex(day_dates, method="ffill").values

    # (target weights renormalized over valid names, prices) per session
    day_data: list[tuple[np.ndarray, np.ndarray]] = []
    for i, wd in enumerate(days):
        w = np.array([wd.get(t, 0.0) for t in valid], dtype=float)
        sm = w.sum()
        px = price_rows[i if len(price_rows) > 1 else 0]
        if sm <= 0 or not np.all(np.isfinite(px)):
            continue
        day_data.append((w / sm, px))
    if not day_data:
        return empty

    def impl_te(aum_bn: float, w: np.ndarray, px: np.ndarray) -> float:
        lots, _ = compute_lot_positions(aum_bn * 1e9, w, px)
        w_act = lots * LOT_SIZE * px / (aum_bn * 1e9)
        d = w_act - w
        return float(np.sqrt(max(float(d @ cov @ d), 0.0)))

    def te_med(aum_bn: float) -> float:
        return float(np.median([impl_te(aum_bn, w, px) for w, px in day_data]))

    def search(target: float) -> float:
        lo, hi = 0.01, 10_000.0
        if te_med(hi) > target:
            hi = 100_000.0
        for _ in range(34):
            mid = (lo + hi) / 2.0
            if te_med(mid) <= target:
                hi = mid
            else:
                lo = mid
        return math.ceil(hi * 100) / 100

    min_bn = search(tol)
    rec_bn = search(rec_tol)

    # Bottleneck: the largest weight deviation at min_aum, on the latest session
    w_last, px_last = day_data[-1]
    lots, _ = compute_lot_positions(min_bn * 1e9, w_last, px_last)
    w_act = lots * LOT_SIZE * px_last / (min_bn * 1e9)
    bi = int(np.abs(w_act - w_last).argmax())

    # Median TE by AUM; the current AUM is inserted when it falls inside the ladder
    base = aum_tiers or AUM_TIERS_BN
    extra = ([current_aum_bn] if current_aum_bn
             and min(base) <= current_aum_bn <= max(base) else [])
    tiers = sorted(set(base + extra))
    te_curve = [{"aum_bn": round(a, 3),
                 "te_pct": round(te_med(a) * 100, 2),
                 "is_current": current_aum_bn is not None and abs(a - current_aum_bn) < 1e-9}
                for a in tiers]

    return {
        "min_aum_bn": float(min_bn),
        "recommended_aum_bn": float(rec_bn),
        "bottleneck_ticker": valid[bi],
        "bottleneck_weight_pct": round(float(w_last[bi]) * 100, 2),
        "te_curve": te_curve,
    }
