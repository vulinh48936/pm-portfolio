"""Orchestration for the router: result cache, compare, weight grid.

Interactive requests run in-process so the PM sees the traceback of their own code;
the daily job uses runner.run_safe (child process with a timeout) instead.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.lab.benchmark import load_ftse_drift_weights
from app.lab.config import LabConfig
from app.lab.runner import forced_rebalance, run_backtest, spec_hash

# Backtest results keyed by (spec, config), so compare and weight grid reuse one run.
_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_MAX = 64


def run_cached(spec: dict[str, Any], config: LabConfig) -> dict[str, Any]:
    h = spec_hash(spec, config)
    if h not in _CACHE:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[h] = run_backtest(spec, config)
    return _CACHE[h]


def forced_cached(spec: dict[str, Any], config: LabConfig) -> dict[str, Any]:
    """Like run_cached but for forced_rebalance; separate key, same cache."""
    h = spec_hash(spec, config) + ":forced"
    if h not in _CACHE:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[h] = forced_rebalance(spec, config)
    return _CACHE[h]


def _trim(res: dict[str, Any]) -> dict[str, Any]:
    """Drop the heavy weight matrix from the backtest/compare payload."""
    return {k: v for k, v in res.items() if k not in ("w_matrix", "weight_dates")}


def backtest(spec: dict[str, Any], config: LabConfig) -> dict[str, Any]:
    return _trim(run_cached(spec, config))


def compare(strategies: list[dict[str, Any]], config: LabConfig) -> dict[str, Any]:
    """Run N strategies on one config; the benchmark curve is returned once."""
    from app.lab.liquidity import capacity_summary

    items, bench_cum, vnindex_cum, dates = [], None, None, None
    bench_metrics, vnindex_metrics = None, None
    for s in strategies:
        res = run_cached(s["spec"], config)
        if dates is None:
            dates, bench_cum, vnindex_cum = res["dates"], res["bench_cum"], res["vnindex_cum"]
            bench_metrics, vnindex_metrics = res["bench_metrics"], res["vnindex_metrics"]
        cap = capacity_summary(res["weights_latest"], config.universe, config.aum_bn,
                               as_of=config.end_date)
        items.append({
            "name": s["name"],
            "metrics": res["metrics"],
            "port_cum": res["port_cum"],
            "max_weight_series": res["max_weight_series"],
            # Invested share over time; None when the strategy has no regime overlay.
            # The UI plots cash% = 100 - exposure.
            "exposure_series": res["exposure_series"],
            "capacity": cap,
        })
    return {"dates": dates, "bench_cum": bench_cum, "vnindex_cum": vnindex_cum,
            "bench_metrics": bench_metrics, "vnindex_metrics": vnindex_metrics,
            "strategies": items}


def weight_grid(strategies: list[dict[str, Any]], config: LabConfig,
                date: str | None = None,
                force_rebalance: bool = False) -> dict[str, Any]:
    """Per-ticker weights of each method plus FTSE on one date (default: last session).

    `force_rebalance=True` forces a rebalance on the last data session and shows the
    weights AFTER it, instead of the drifted weights currently held. That mode ignores
    `date` because force only applies at end_date (see runner.forced_rebalance).
    """
    tickers = config.universe
    grid: dict[str, dict[str, float]] = {t: {} for t in tickers}
    used_date = date
    rebalance_date = None

    for s in strategies:
        if force_rebalance:
            fr = forced_cached(s["spec"], config)
            used_date, rebalance_date = fr["data_date"], fr["rebalance_date"]
            row = [fr["weights_after"][t] for t in tickers]
        else:
            res = run_cached(s["spec"], config)
            wdates = res["weight_dates"]
            idx = len(wdates) - 1 if not date else _nearest_idx(wdates, date)
            used_date = wdates[idx]
            row = res["w_matrix"][idx]
        for i, t in enumerate(tickers):
            grid[t][s["name"]] = round(row[i] * 100, 2)

    # Benchmark column uses DRIFTED weights, the same basis as the strategy weights;
    # mid-period the static target differs a lot from what is held.
    cal = pd.DatetimeIndex([pd.Timestamp(used_date)])
    w_bench = load_ftse_drift_weights(cal, tickers)[0]
    for i, t in enumerate(tickers):
        grid[t]["FTSE"] = round(float(w_bench[i]) * 100, 2)

    rows = [{"ticker": t, **grid[t]} for t in tickers]
    return {"date": used_date, "rows": rows,
            "columns": [s["name"] for s in strategies] + ["FTSE"],
            "forced": force_rebalance, "rebalance_date": rebalance_date}


def _nearest_idx(dates: list[str], target: str) -> int:
    arr = pd.DatetimeIndex(dates)
    pos = arr.searchsorted(pd.Timestamp(target))
    return int(min(max(pos, 0), len(dates) - 1))
