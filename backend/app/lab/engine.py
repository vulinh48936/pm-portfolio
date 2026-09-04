"""StrategyEngine: day-by-day backtest of one Strategy, with no look-ahead.

Behaviour: hold the benchmark during warm-up, cap with a waterfall, drift weights with
prices. No look-ahead is structural: w_tv[t] is set at the close of t-1,
port_ret[t] = w_tv[t] . rets[t], and drift uses rets[t].
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.lab.config import LabConfig
from app.lab.features import FeatureView, build_extra_panels
from app.lab.lib import cap_weights
from app.lab.rules import apply_hard_rules
from app.lab.strategy import Ctx, Strategy


# Rebalance schedule

def _period_first_indices(calendar: pd.DatetimeIndex, freq: str) -> list[int]:
    """Indices of the first trading day of each period ('M' month, 'Q' quarter)."""
    per = calendar.to_period(freq)
    idx, prev = [], None
    for i, p in enumerate(per):
        if p != prev:
            idx.append(i)
            prev = p
    return idx


def _schedule_set(calendar: pd.DatetimeIndex, schedule: str) -> set[int]:
    if schedule == "daily":
        return set(range(len(calendar)))
    if schedule == "monthly":
        return set(_period_first_indices(calendar, "M"))
    if schedule == "quarterly":
        return set(_period_first_indices(calendar, "Q"))
    if schedule == "none":
        return set()
    raise ValueError(f"rebalance_schedule không hợp lệ: {schedule!r}")


# Move policies (turnover control)

def _one_way_turnover(w_new: np.ndarray, w_old: np.ndarray) -> float:
    return 0.5 * float(np.abs(w_new - w_old).sum())


def _apply_move(strategy: Strategy, w_drift: np.ndarray,
                w_target: np.ndarray) -> tuple[np.ndarray, float]:
    """Apply the strategy move policy against the DRIFTED weights.

    `w_drift` is what is actually held just before the rebalance session, not the target
    set at the previous period; every threshold below is measured against it.
    """
    policy = strategy.move_policy
    if policy == "full":
        return w_target, _one_way_turnover(w_target, w_drift)
    if policy == "band":
        move = np.abs(w_target - w_drift) >= strategy.band
        w_new = np.where(move, w_target, w_drift)
        s = w_new.sum()
        if s > 0:
            w_new = w_new / s
        return w_new, _one_way_turnover(w_new, w_drift)
    if policy == "budget":
        raw_to = _one_way_turnover(w_target, w_drift)
        if raw_to <= strategy.budget or raw_to < 1e-12:
            return w_target, raw_to
        scale = strategy.budget / raw_to
        w_new = w_drift + scale * (w_target - w_drift)
        s = w_new.sum()
        if s > 0:
            w_new = w_new / s
        return w_new, _one_way_turnover(w_new, w_drift)
    if policy == "maxmove":
        m = float(strategy.max_move)
        if m <= 0.0:
            return w_drift.copy(), 0.0
        lo = np.maximum(w_drift - m, 0.0)   # sell at most m, never negative
        hi = w_drift + m                    # buy at most m
        w_new = np.clip(w_target, lo, hi)
        # Clipping per ticker breaks sum(w)=1, because the clipped deltas no longer
        # cancel out. Do NOT normalize: dividing by the sum rescales every ticker and
        # breaks the constraint just applied. Push the remainder into tickers that still
        # have room, proportionally (same waterfall idea as cap_weights), which keeps
        # both sum(w)=1 and |dw| <= m.
        for _ in range(100):
            resid = 1.0 - float(w_new.sum())
            if abs(resid) < 1e-12:
                break
            room = (hi - w_new) if resid > 0.0 else (w_new - lo)
            tot = float(room.sum())
            if tot < 1e-12:
                break                        # no room left; cap_weights fixes the sum afterwards
            w_new = w_new + np.sign(resid) * room * (min(abs(resid), tot) / tot)
        return w_new, _one_way_turnover(w_new, w_drift)
    raise ValueError(f"move_policy không hợp lệ: {policy!r}")


def _drawdown_from_peak(rets_hist: np.ndarray, w: np.ndarray, window: int = 252) -> float:
    """Drawdown of the basket (w . stock_rets) from its `window`-day peak; negative."""
    idx_rets = rets_hist[-window:] @ w
    if len(idx_rets) < 2:
        return 0.0
    cum = np.cumprod(1.0 + idx_rets)
    return float(cum[-1] / cum.max()) - 1.0


# Engine

class StrategyEngine:
    """Backtest a Strategy over the universe and benchmark."""

    def __init__(self, config: LabConfig):
        self.config = config

    def run(self, strategy: Strategy, closes_arr: np.ndarray,
            calendar: pd.DatetimeIndex, w_bench_tv: np.ndarray,
            tickers: list[str], adtv: np.ndarray | None = None,
            frob_z: pd.Series | None = None) -> dict:
        """Run the backtest.

        Args:
            strategy:    validated Strategy instance
            closes_arr:  (T, N) close prices aligned to the calendar
            calendar:    DatetimeIndex of length T
            w_bench_tv:  (T, N) time-varying benchmark weights
            tickers:     N tickers, column order
            adtv:        (N,) ADTV vector, optional
            frob_z:      regime signal series, optional, exposed as ctx.frob_z

        Returns w_tv (T,N), port_ret (T,), turnover_log (DataFrame) and rebal_idx.
        """
        cfg = self.config
        T, N = closes_arr.shape
        # rets keeps NaN (not yet listed) for eligibility; rets_filled (NaN->0) drives pnl and drift
        rets = np.full_like(closes_arr, np.nan)
        rets[1:] = closes_arr[1:] / closes_arr[:-1] - 1.0
        ret_valid = ~np.isnan(rets)
        rets_filled = np.where(ret_valid, np.nan_to_num(rets, nan=0.0), 0.0)

        schedule_set = _schedule_set(calendar, strategy.rebalance_schedule)
        frob_arr = (frob_z.reindex(calendar).fillna(0.0).values
                    if frob_z is not None else np.zeros(T))
        extra = build_extra_panels(tickers, calendar)

        w_tv = np.zeros((T, N))
        port_ret = np.zeros(T)
        turnover_log: list[dict] = []

        w_current: np.ndarray | None = None
        last_rebal_t = cfg.warm_up

        for t in range(T):
            if t >= cfg.warm_up and w_current is not None:
                dd = _drawdown_from_peak(rets_filled[1:t], w_current, cfg.cov_window)
                ctx = Ctx(
                    t=t, date=calendar[t], drawdown=dd, frob_z=float(frob_arr[t]),
                    days_since_rebal=t - last_rebal_t, max_weight=float(w_current.max()),
                    w_current=w_current, is_scheduled=(t in schedule_set),
                )
                if strategy.should_rebalance(ctx):
                    w_alloc = self._allocate_dynamic(
                        strategy, rets, ret_valid, closes_arr, w_bench_tv[t],
                        t, tickers, adtv, extra, ctx,
                    )
                    # A strategy-level ADTV floor applies to the WHOLE vector, including
                    # the passive short-history names that allocate() never sees.
                    sfloor = float(getattr(strategy, "adtv_floor_bn", 0.0) or 0.0)
                    if sfloor > 0.0 and adtv is not None:
                        w_alloc = np.where(adtv >= sfloor, w_alloc, 0.0)
                    w_alloc = apply_hard_rules(w_alloc, cfg, adtv)
                    w_raw = cap_weights(w_alloc, cfg.cap)
                    w_new, tno = _apply_move(strategy, w_current, w_raw)
                    # Force-sell names that left the FTSE basket, overriding the no-trade
                    # band: otherwise a stale position below the band would linger.
                    w_new = w_new * (w_bench_tv[t] > 0)
                    w_current = cap_weights(w_new, cfg.cap)
                    last_rebal_t = t
                    turnover_log.append({"t": t, "date": calendar[t], "turnover": tno,
                                         "rebalanced": True, "dd_pct": round(dd * 100, 2),
                                         "frob_z": round(float(frob_arr[t]), 2)})
            elif w_current is None:
                w_current = w_bench_tv[t].copy()   # warm-up: hold benchmark (FTSE target)

            w_tv[t] = w_current
            port_ret[t] = float(w_current @ rets_filled[t])

            # Drift from the start of t to the start of t+1 using day t returns
            if t < T - 1:
                growth = w_current * (1.0 + rets_filled[t])
                gsum = growth.sum()
                if gsum > 0:
                    w_current = growth / gsum

        tlog = pd.DataFrame(turnover_log)
        return {
            "w_tv": w_tv,
            "port_ret": port_ret,
            "turnover_log": tlog,
            # Days that actually rebalanced, not the schedule: should_rebalance can skip
            # a scheduled day or fire off-cycle. liquidity.py measures dw at the latest of
            # these; using the schedule would pick a day with no trades and dw about 0.
            "rebal_idx": sorted(int(t) for t in tlog["t"]) if len(tlog) else [],
        }

    def _allocate_dynamic(self, strategy: Strategy, rets: np.ndarray,
                          ret_valid: np.ndarray, closes_arr: np.ndarray,
                          w_target: np.ndarray, t: int, tickers: list[str],
                          adtv: np.ndarray | None, extra: dict, ctx: Ctx) -> np.ndarray:
        """Dynamic universe, split into three groups:

          - not listed yet, or not in the basket (w_target=0)   -> weight 0
          - short history (< cov_window continuous sessions)    -> held at benchmark weight
          - eligible (>= cov_window)                            -> strategy.allocate

        The short-history group keeps its benchmark weight; the remaining budget
        (1 - sum of those weights) is what allocate() distributes. The strategy only sees
        a FeatureView of the eligible group, which keeps the covariance clean and PSD.
        """
        cfg = self.config
        N = len(tickers)
        cw = cfg.cov_window
        univ = w_target > 0
        # The eligibility window must match the covariance FeatureView uses:
        # rets[1:t][-cw:], dropping row 0 whose return is structurally NaN. Including
        # row 0 would fail exactly at t=cw and delay the first optimization by a quarter.
        full_hist = (ret_valid[max(1, t - cw):t].all(axis=0) if t >= cw
                     else np.zeros(N, dtype=bool))
        eligible = univ & full_hist
        short = univ & ~eligible

        if int(eligible.sum()) < 2:
            return w_target.copy()   # too few names to optimize: hold the benchmark

        idx = np.where(eligible)[0]
        sub_extra = {k: v[:, idx] for k, v in extra.items()}
        sub_adtv = adtv[idx] if adtv is not None else None
        feat = FeatureView(rets[:, idx], closes_arr[:, idx], t,
                           [tickers[i] for i in idx], sub_adtv, sub_extra)
        wb = w_target[idx]
        wb = wb / wb.sum() if wb.sum() > 0 else np.ones(len(idx)) / len(idx)

        w_e = np.clip(np.asarray(strategy.allocate(feat, wb, ctx), dtype=float), 0.0, None)
        se = w_e.sum()
        w_e = w_e / se if se > 0 else np.ones(len(idx)) / len(idx)

        w_alloc = np.zeros(N)
        w_alloc[short] = w_target[short]                 # passive at benchmark weight
        budget_short = float(w_alloc[short].sum())
        w_alloc[idx] = w_e * (1.0 - budget_short)        # eligible group splits the remaining budget
        return w_alloc
