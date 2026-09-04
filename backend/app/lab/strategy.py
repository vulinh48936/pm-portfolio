"""The `Strategy` contract that generated code must implement.

A strategy subclasses Strategy, overrides `allocate` and optionally
`should_rebalance`. Class attributes declare the rebalance schedule and move policy;
StrategyEngine reads them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.lab.features import FeatureView


@dataclass
class Ctx:
    """State at one decision point, passed to should_rebalance and allocate."""

    t: int                       # day index in the calendar
    date: object                 # pd.Timestamp
    drawdown: float              # current portfolio drawdown (negative), 0 before warm-up
    frob_z: float                # regime-shift z-score for this day
    days_since_rebal: int        # sessions since the last rebalance
    max_weight: float            # largest single-name weight held
    w_current: np.ndarray | None # weights held (already drifted), None before init
    is_scheduled: bool = False   # is today a scheduled rebalance day


class Strategy:
    """Base contract: override `allocate` (required) and `should_rebalance` (optional).

    Rebalance attributes:
        rebalance_schedule: "daily" | "monthly" | "quarterly" | "none"
        move_policy:        "band" | "budget" | "maxmove" | "full"
        band:               no-trade threshold (move_policy="band")
        budget:             one-way turnover cap for the WHOLE book per period
        max_move:           per-ticker |dw| cap per period (move_policy="maxmove")

    The three move policies limit different things:
        band    — drops SMALL trades only; once past the threshold it jumps fully to target.
        budget  — book-level cap: the whole move vector is scaled to fit total turnover,
                  so one ticker can consume the entire budget.
        maxmove — per-ticker cap; the only one that stops a single 0% -> 25% jump.
    All three compare against weights ALREADY DRIFTED by prices up to the rebalance
    session (what is actually held), not the target set at the previous period.
    """

    rebalance_schedule: str = "quarterly"
    move_policy: str = "band"
    band: float = 0.015
    budget: float = 0.10
    max_move: float = 0.05

    # Optional regime cash overlay, applied in runner.py; it scales gross exposure and
    # never touches composition. Signal: FTSE index below its MA -> exposure drops to
    # regime_floor, else 1.0. Shifted one session (no look-ahead); cash earns nothing.
    #   regime_guard:   None | "ftse_ma"  (None = always fully invested)
    #   regime_ma:      MA window on the index, e.g. 200
    #   regime_floor:   exposure kept when risk-off (0.0 = all cash, 0.5 = half)
    #   regime_confirm: MA state must hold N sessions to count (1 = off); filters whipsaw
    #   regime_step:    None = follow the signal DAILY (trade to target every session)
    #                   "rebalance" = reset only on rebalance days; in between the cash
    #                                 leg is buy-and-hold, so exposure drifts with prices
    #                   "trigger"   = "rebalance" plus an emergency reset when the MA
    #                                 state flips (a few times a year)
    #                   The two stepped modes suit SDI, where clients track weight
    #                   versions instead of changing weights daily.
    regime_guard: str | None = None
    regime_ma: int = 200
    regime_floor: float = 0.0
    regime_confirm: int = 1
    regime_step: str | None = None

    def allocate(self, feat: FeatureView, w_bench: np.ndarray, ctx: Ctx) -> np.ndarray:
        """Return target weights: sum=1, long-only, pre-cap. Must be overridden."""
        raise NotImplementedError("Strategy phải implement allocate().")

    def should_rebalance(self, ctx: Ctx) -> bool:
        """Optional off-schedule trigger. Defaults to following the schedule.

        Override to:
        - filter the schedule: `return ctx.is_scheduled and ctx.drawdown < -0.08`
        - add off-cycle triggers: `return ctx.is_scheduled or ctx.frob_z > 2.0`
        - go trigger-only: set rebalance_schedule="none" and `return ctx.frob_z > 2.0`
        """
        return ctx.is_scheduled
