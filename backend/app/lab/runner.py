"""Orchestrate a backtest: load data, run the strategy through the engine, build metrics.

`run_backtest` runs in-process; `run_safe` runs it in a child process with a timeout so
broken or looping strategy code cannot hang the server.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from app.lab.benchmark import (
    build_time_varying_weights, compute_frob_z_series, load_ftse_drift_ret,
    load_vnindex_ret,
)
from app.lab.config import LabConfig
from app.lab.engine import StrategyEngine
from app.lab.metrics import compute_metrics, index_metrics
from app.lab.presets import PRESETS
from app.lab.sandbox import load_strategy


def _resolve_code(spec: dict[str, Any]) -> str:
    """spec is {"code": "..."} or {"preset": "risk_parity"}."""
    if spec.get("code"):
        return spec["code"]
    preset = spec.get("preset")
    if preset not in PRESETS:
        raise ValueError(f"Preset không tồn tại: {preset}. Có: {sorted(PRESETS)}")
    return PRESETS[preset]


def _load_market(config: LabConfig):
    """Return (calendar, closes_arr, w_bench, bench_ret, adtv, frob_z, vis).

    Loads about 15 extra months before start_date so a 252-day covariance and momentum
    windows are warm on the first displayed day. `vis` is the index of start_date in that
    extended calendar; run_backtest slices [:vis] off afterwards. `end_date` trims the
    calendar and freezes ADTV there, so liquidity is never measured on future data.
    """
    from app.lab.features import PriceFeatureProvider

    tickers = config.universe
    buffer_start = (pd.Timestamp(config.start_date)
                    - pd.DateOffset(months=15)).strftime("%Y-%m-%d")
    cal_full, closes_full, _rets_full, adtv = PriceFeatureProvider().load_panel(
        tickers, start=buffer_start, end=config.end_date)

    vis = int(cal_full.searchsorted(pd.Timestamp(config.start_date)))
    if vis >= len(cal_full):
        from app.services.csv_data import data_coverage
        raise ValueError(
            f"start_date {config.start_date} nằm ngoài vùng dữ liệu "
            f"(chỉ có tới {data_coverage()[1]})."
        )
    # side='right' makes end_date inclusive when it is a trading day, without spilling
    # into the next session when it falls on a holiday.
    e = (int(cal_full.searchsorted(pd.Timestamp(config.end_date), side="right"))
         if config.end_date else len(cal_full))
    if e <= vis:
        raise ValueError(
            f"Không có phiên giao dịch nào trong khoảng {config.start_date} → "
            f"{config.end_date}."
        )
    calendar = cal_full[:e]          # keep the leading buffer; the engine needs a warm covariance
    closes_arr = closes_full[:e]

    # avail[t,i]: ticker i has a price on day t (not yet listed -> NaN -> False)
    avail = ~np.isnan(closes_arr)
    # Anchor for warm-up and the three-group split: FTSE target weights, masked and renormalized
    w_bench = build_time_varying_weights(calendar, tickers, avail=avail)
    # Actual benchmark return: the drift series from index_ftse.csv
    bench_ret = load_ftse_drift_ret(calendar)
    # frob_z is computed only on tickers with a full history; not-yet-listed names
    # (NaN -> 0) would corrupt the correlation matrix and flatten the signal.
    listed_all = ~np.isnan(closes_arr).any(axis=0)
    try:
        frob_z = (compute_frob_z_series(closes_arr[:, listed_all], calendar)
                  if int(listed_all.sum()) >= 5 else None)
    except Exception:
        frob_z = None
    return calendar, closes_arr, w_bench, bench_ret, adtv, frob_z, vis


def _regime_exposure(
    strategy, bench_ret: np.ndarray, return_raw: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray] | None:
    """Exposure in [floor, 1] from the index trend (level vs MA), over the extended
    calendar so the MA is well formed on the first displayed day.

    Returns None when the strategy has no regime_guard. No look-ahead: exposure[t] uses
    the signal as of t-1, matching how the engine sets w_current.

    `return_raw=True` also returns the unshifted signal; forced_rebalance needs raw[T-1],
    the signal at the last data session.
    """
    guard = getattr(strategy, "regime_guard", None)
    if not guard:
        return None
    ma_win = int(getattr(strategy, "regime_ma", 200))
    floor = float(getattr(strategy, "regime_floor", 0.0))
    level = np.cumprod(1.0 + np.nan_to_num(bench_ret))            # FTSE index level
    ma = pd.Series(level).rolling(ma_win, min_periods=1).mean().to_numpy()
    # Optional dual-MA vote (`regime_ma2`): each MA the index sits above adds
    # (1-floor)/2 of exposure, giving three levels instead of two and less whipsaw.
    ma2_win = getattr(strategy, "regime_ma2", None)
    if ma2_win:
        ma2 = pd.Series(level).rolling(int(ma2_win), min_periods=1).mean().to_numpy()
        step = (1.0 - floor) / 2.0
        raw = floor + step * (level >= ma) + step * (level >= ma2)
    else:
        raw = np.where(level >= ma, 1.0, floor)
    # Optional confirmation (`regime_confirm`): a new state must hold N consecutive
    # sessions before it counts, which filters whipsaw around the MA.
    confirm = int(getattr(strategy, "regime_confirm", 1) or 1)
    if confirm > 1:
        conf = raw.copy()
        cur, run = raw[0], 1
        for t in range(1, len(raw)):
            run = run + 1 if abs(raw[t] - raw[t - 1]) < 1e-9 else 1
            if run >= confirm:
                cur = raw[t]
            conf[t] = cur
        raw = conf
    e = np.empty_like(raw)
    e[0] = 1.0
    e[1:] = raw[:-1]                                              # shift t-1 (no look-ahead)
    return (e, raw) if return_raw else e


def _step_exposure(e_sig: np.ndarray, port_eq: np.ndarray, rebal_set: set[int],
                   trigger: bool, return_state: bool = False,
                   ) -> np.ndarray | tuple[np.ndarray, float, float]:
    """Stepped exposure, suitable for SDI: instead of tracking the signal daily, exposure
    is only reset on a rebalance day, plus, with `trigger`, when the signal state flips
    mid-period (an emergency weight version, a few times a year).

    Between resets the cash leg is buy-and-hold, so exposure drifts with prices:
    e[t+1] = e[t](1+r) / (1 + e[t]r). That is what a client holding one static weight
    version actually experiences.

    `return_state=True` also returns the exposure drifted to the start of session T and
    the last discrete target, which forced_rebalance needs.
    """
    T = len(e_sig)
    e = np.ones(T)
    e_cur = 1.0     # exposure actually held, drifting with prices
    state = 1.0     # last discrete target that was set
    for t in range(T):
        changed = abs(e_sig[t] - state) > 1e-9
        if changed and (t in rebal_set or trigger):
            e_cur = state = e_sig[t]
        e[t] = e_cur
        r = float(port_eq[t])
        g = 1.0 + e_cur * r
        if g > 1e-9:
            e_cur = e_cur * (1.0 + r) / g
    return (e, e_cur, state) if return_state else e


def run_backtest(spec: dict[str, Any], config: LabConfig) -> dict[str, Any]:
    """Run one backtest and return the full result, including the weight matrix."""
    code = _resolve_code(spec)
    strategy_cls = load_strategy(code)
    strategy = strategy_cls()

    calendar, closes_arr, w_bench, bench_ret, adtv, frob_z, vis = _load_market(config)
    res = StrategyEngine(config).run(
        strategy, closes_arr, calendar, w_bench, config.universe, adtv, frob_z,
    )

    # Drop the warm-up buffer; keep only the displayed window from start_date on.
    vcal = calendar[vis:]
    v_port_ret = res["port_ret"][vis:]
    v_w_tv = res["w_tv"][vis:]
    v_bench = bench_ret[vis:]
    v_wbench = w_bench[vis:]
    _tlog = res["turnover_log"]
    v_tlog = _tlog[_tlog["t"] >= vis].copy() if len(_tlog) else _tlog

    # Optional regime cash overlay: the engine decides composition, the overlay only
    # scales gross exposure and the shortfall is cash. `regime_step` picks how it is
    # applied: None follows the signal daily (not usable for SDI, since every change is
    # a new weight version), "rebalance" resets only on rebalance days, "trigger" adds
    # an emergency reset when the MA state flips.
    exposure = _regime_exposure(strategy, bench_ret)
    v_exposure = None
    if exposure is not None:
        step_mode = getattr(strategy, "regime_step", None)
        if step_mode in ("rebalance", "trigger"):
            _tl = res["turnover_log"]
            rebal_set = set(_tl["t"].astype(int).tolist()) if len(_tl) else set()
            exposure = _step_exposure(exposure, res["port_ret"], rebal_set,
                                      trigger=(step_mode == "trigger"))
        elif step_mode:
            raise ValueError(f"regime_step không hợp lệ: {step_mode!r} "
                             "(cho phép: None, 'rebalance', 'trigger').")
        v_exposure = exposure[vis:]
        v_port_ret = v_port_ret * v_exposure          # cash earns nothing
        v_w_tv = v_w_tv * v_exposure[:, None]          # sum below 1 means the rest is cash

    m = compute_metrics(v_port_ret, v_bench, v_w_tv, v_wbench,
                        v_tlog, config.universe)

    weights_latest = {t: round(float(v_w_tv[-1, i]), 4)
                      for i, t in enumerate(config.universe)}
    adtv_map = {t: float(adtv[i]) for i, t in enumerate(config.universe)}
    # Feasibility TE: median over the last ~20 sessions, covariance over 252.
    _FEAS_DAYS = 20
    w_hist = [{t: float(row[i]) for i, t in enumerate(config.universe) if row[i] > 1e-9}
              for row in v_w_tv[-_FEAS_DAYS:]]
    dates_hist = list(vcal[-_FEAS_DAYS:])
    from app.lab.feasibility import min_aum
    from app.lab.rules import rule_warnings
    try:
        feasibility = min_aum(weights_latest, current_aum_bn=config.aum_bn,
                              weights_history=w_hist, dates=dates_hist,
                              as_of=config.end_date)
    except Exception:
        feasibility = {}
    warnings = rule_warnings(weights_latest, config, adtv_map)

    port_cum = (np.cumprod(1.0 + v_port_ret[1:]) * 100).tolist()
    bench_cum = (np.cumprod(1.0 + v_bench[1:]) * 100).tolist()
    vnindex_ret = load_vnindex_ret(vcal)                # second reference line
    vnindex_cum = (np.cumprod(1.0 + vnindex_ret[1:]) * 100).tolist()
    # Metrics for the two reference indices, shown next to the strategy in Compare
    bench_metrics = index_metrics(v_bench, v_bench)
    vnindex_metrics = index_metrics(vnindex_ret, v_bench)
    dates = [d.strftime("%Y-%m-%d") for d in vcal[1:]]
    max_w_series = (v_w_tv.max(axis=1) * 100).tolist()
    # Invested share: 100 = fully invested, below that the overlay holds cash
    exposure_series = ((v_exposure[1:] * 100).tolist()
                       if v_exposure is not None else None)

    return {
        "metrics": m,
        "dates": dates,
        "port_cum": port_cum,
        "bench_cum": bench_cum,
        "vnindex_cum": vnindex_cum,
        "bench_metrics": bench_metrics,
        "vnindex_metrics": vnindex_metrics,
        "exposure_series": exposure_series,
        "max_weight_series": max_w_series,
        "weights_latest": weights_latest,
        "feasibility": feasibility,
        "warnings": warnings,
        # full weight matrix (picklable) for the fixed-date weight grid
        "w_matrix": np.round(v_w_tv, 6).tolist(),
        "weight_dates": [d.strftime("%Y-%m-%d") for d in vcal],
        "rebal_idx": [int(i - vis) for i in res["rebal_idx"] if vis <= i < len(calendar)],
        "rebalance_schedule": strategy.rebalance_schedule,
        "move_policy": strategy.move_policy,
    }


def forced_rebalance(spec: dict[str, Any], config: LabConfig) -> dict[str, Any]:
    """Force ONE rebalance at t = T, the session right after the last data day.

    A backtest only rebalances on schedule, so the last row is what is currently held
    after drifting with prices, not a fresh target. This answers a different question:
    what would the book look like if we rebalanced right now.

    It replays the exact order used by StrategyEngine.run():
        allocate -> strategy ADTV floor -> hard rules -> cap -> move policy against the
        DRIFTED book -> force-sell names that left the basket -> cap

    No look-ahead: the FeatureView cutoff is t=T, so it sees up to end_date, and the
    regime uses the signal at T-1. The basket is the one effective on the ORDER date;
    FTSE publishes new constituents before they take effect, so this is not look-ahead.

    Returns composition already scaled by exposure, same convention as w_matrix, so a
    sum below 1 means the rest is cash.
    """
    from app.lab.engine import _apply_move, _drawdown_from_peak
    from app.lab.features import build_extra_panels
    from app.lab.lib import cap_weights
    from app.lab.rules import apply_hard_rules
    from app.lab.strategy import Ctx

    code = _resolve_code(spec)
    strategy = load_strategy(code)()

    calendar, closes_arr, w_bench, bench_ret, adtv, frob_z, _vis = _load_market(config)
    T = len(calendar)
    last_day = calendar[-1]

    engine = StrategyEngine(config)
    res = engine.run(strategy, closes_arr, calendar, w_bench, config.universe, adtv, frob_z)
    w_tv = res["w_tv"]

    rets = np.full_like(closes_arr, np.nan)
    rets[1:] = closes_arr[1:] / closes_arr[:-1] - 1.0
    ret_valid = ~np.isnan(rets)
    rets_filled = np.where(ret_valid, np.nan_to_num(rets, nan=0.0), 0.0)

    # w_tv[T-1] is the weight at the start of the last session; drift it through that
    # session to get the book at the closing prices
    w_book = w_tv[T - 1] * (1.0 + rets_filled[T - 1])
    bsum = w_book.sum()
    if bsum <= 1e-12:
        raise ValueError("Book rỗng tại phiên cuối — không ép rebalance được.")
    w_book = w_book / bsum

    # Ctx at t=T, built exactly as the engine loop would
    tlog = res["turnover_log"]
    last_rebal_t = int(tlog["t"].iloc[-1]) if len(tlog) else config.warm_up
    frob_arr = (frob_z.reindex(calendar).fillna(0.0).values
                if frob_z is not None else np.zeros(T))
    ctx = Ctx(t=T, date=last_day,
              drawdown=_drawdown_from_peak(rets_filled[1:T], w_book, config.cov_window),
              frob_z=float(frob_arr[T - 1]),      # latest known regime signal
              days_since_rebal=T - last_rebal_t,
              max_weight=float(w_book.max()), w_current=w_book, is_scheduled=True)

    # Use the basket effective on the ORDER date, not on the last data day. The two fall
    # in different review periods whenever the order date crosses an effective_date, and
    # then w_bench[T-1] is stale: new entrants would be forced to 0 and departures kept.
    # Not look-ahead: FTSE publishes the new constituents before they take effect.
    # Availability is still measured at the last session.
    rebal_ts = last_day + pd.tseries.offsets.BDay(1)
    w_bench_next = build_time_varying_weights(
        pd.DatetimeIndex([rebal_ts]), config.universe,
        avail=(~np.isnan(closes_arr[T - 1:T])))[0]

    extra = build_extra_panels(config.universe, calendar)
    w_alloc = engine._allocate_dynamic(strategy, rets, ret_valid, closes_arr,
                                       w_bench_next, T, config.universe, adtv, extra, ctx)
    sfloor = float(getattr(strategy, "adtv_floor_bn", 0.0) or 0.0)
    if sfloor > 0.0 and adtv is not None:
        w_alloc = np.where(adtv >= sfloor, w_alloc, 0.0)
    w_alloc = apply_hard_rules(w_alloc, config, adtv)
    w_raw = cap_weights(w_alloc, config.cap)
    w_new, turnover = _apply_move(strategy, w_book, w_raw)
    w_new = w_new * (w_bench_next > 0)            # force-sell names that left the basket
    w_after = cap_weights(w_new, config.cap)

    # The non-forced grid shows w_tv already scaled by exposure, so the forced result
    # must be scaled the same way or the two modes disagree for overlay strategies.
    exposure = None
    _reg = _regime_exposure(strategy, bench_ret, return_raw=True)
    if _reg is not None:
        e_sig, raw = _reg
        exposure = float(raw[T - 1])              # signal as of the last session
        step_mode = getattr(strategy, "regime_step", None)
        if step_mode in ("rebalance", "trigger"):
            _tl = res["turnover_log"]
            rebal_set = set(_tl["t"].astype(int).tolist()) if len(_tl) else set()
            _e, e_cur, state = _step_exposure(e_sig, res["port_ret"], rebal_set,
                                              trigger=(step_mode == "trigger"),
                                              return_state=True)
            # Stepped mode only resets exposure when the signal differs from the last
            # target; otherwise the cash leg keeps drifting. Using raw[T-1] directly
            # would restate cash every period and diverge from the backtest.
            if abs(exposure - state) <= 1e-9:
                exposure = float(e_cur)
        elif step_mode:
            raise ValueError(f"regime_step không hợp lệ: {step_mode!r} "
                             "(cho phép: None, 'rebalance', 'trigger').")
        w_after = w_after * exposure

    return {
        "data_date": last_day.strftime("%Y-%m-%d"),
        "rebalance_date": rebal_ts.strftime("%Y-%m-%d"),
        "weights_after": {t: float(w_after[i]) for i, t in enumerate(config.universe)},
        "turnover_one_way": float(turnover),
        "exposure": exposure,
        "move_policy": strategy.move_policy,
    }


# Child-process safety

def _worker(spec: dict[str, Any], config_dict: dict[str, Any]) -> dict[str, Any]:
    """Runs in the child process; the result is picklable (lists and dicts only)."""
    return run_backtest(spec, LabConfig(**config_dict))


def run_safe(spec: dict[str, Any], config: LabConfig,
             timeout: float = 60.0) -> dict[str, Any]:
    """Backtest in a child process with a timeout, so a runaway loop cannot hang us.

    Do NOT use `with ProcessPoolExecutor(...)`: its __exit__ calls shutdown(wait=True),
    which waits for the very child that is looping and hangs forever, holding
    daily_job._LOCK so every later job reports "already running". Kill the child first,
    then shutdown(wait=False).
    """
    ex = ProcessPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(_worker, spec, asdict(config))
        try:
            return fut.result(timeout=timeout)
        except FutureTimeout:
            for proc in list(ex._processes.values()):
                proc.kill()
            raise TimeoutError(f"Backtest vượt {timeout}s — code chiến lược có thể bị treo.")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def spec_hash(spec: dict[str, Any], config: LabConfig) -> str:
    blob = json.dumps({"spec": spec, "config": asdict(config)}, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]
