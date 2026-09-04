"""Per-ticker breakdown of excess return versus the benchmark, over a window.

  contrib_i = sum_t (w_strat[t,i] - w_bench_drift[t,i]) * ret[t,i]

Both sides use DRIFTED weights, so the contributions add up to the actual daily excess.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.data.universe_config import TICKER_META
from app.lab.config import LabConfig


def compute_attribution(w_matrix: list[list[float]], config: LabConfig,
                        window_start: str | None = None) -> dict[str, Any]:
    """Contribution per ticker from window_start to the end (default: last ~6 months)."""
    from app.lab.benchmark import load_ftse_drift_weights
    from app.lab.runner import _load_market

    calendar, closes_arr, _w_target, _bench_ret, _adtv, _frob, vis = _load_market(config)
    # Drop the warm-up buffer so the calendar matches w_matrix
    calendar, closes_arr = calendar[vis:], closes_arr[vis:]
    # The benchmark side must be DRIFTED weights like w_strat; with static targets the
    # contributions no longer sum to the actual excess return.
    w_bench = load_ftse_drift_weights(calendar, config.universe)
    w_strat = np.asarray(w_matrix, dtype=float)
    # NaN-safe returns: tickers not yet listed contribute 0
    rets = np.zeros_like(closes_arr)
    with np.errstate(invalid="ignore"):
        rets[1:] = closes_arr[1:] / closes_arr[:-1] - 1.0
    rets = np.nan_to_num(rets, nan=0.0, posinf=0.0, neginf=0.0)

    T = len(calendar)
    if window_start:
        t0 = int(calendar.searchsorted(pd.Timestamp(window_start)))
    else:
        t0 = max(0, T - 126)   # about 6 months of sessions
    t0 = min(max(t0, 0), T - 1)
    win = slice(t0, T)

    contrib = ((w_strat[win] - w_bench[win]) * rets[win]).sum(axis=0) * 100      # pp
    wdiff = (w_strat[win] - w_bench[win]).mean(axis=0) * 100
    stock_ret = (np.prod(1.0 + rets[win], axis=0) - 1.0) * 100
    w_strat_avg = w_strat[win].mean(axis=0) * 100
    w_ftse_avg = w_bench[win].mean(axis=0) * 100

    rows = [{
        "ticker": t,
        "sector": TICKER_META.get(t, {}).get("sector", "?"),
        "w_strat_pct": round(float(w_strat_avg[i]), 2),
        "w_ftse_pct": round(float(w_ftse_avg[i]), 2),
        "wdiff_pct": round(float(wdiff[i]), 2),
        "stock_ret_pct": round(float(stock_ret[i]), 1),
        "contrib_pp": round(float(contrib[i]), 2),
    } for i, t in enumerate(config.universe)]
    rows.sort(key=lambda r: r["contrib_pp"])

    return {
        "window_start": str(calendar[t0].date()),
        "window_end": str(calendar[-1].date()),
        "total_contrib_pp": round(float(contrib.sum()), 1),
        "rows": rows,
    }
