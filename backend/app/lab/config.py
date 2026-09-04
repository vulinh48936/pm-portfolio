"""Config of one lab session: universe, hard rules, rebalance defaults."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.data.universe_config import TICKERS_FTSE


@dataclass
class LabConfig:
    universe: list[str] = field(default_factory=lambda: list(TICKERS_FTSE))
    start_date: str = "2020-01-02"
    end_date: str | None = None       # None = up to the last session available

    # Hard rules, applied after strategy.allocate so a strategy cannot exceed them
    cap: float | None = 0.25
    adtv_floor_bn: float | None = None
    max_names: int | None = None
    min_names: int | None = None

    # Rebalance defaults; a strategy may override them via class attributes
    warm_up: int = 120                # first days are held at benchmark weights
    cov_window: int = 252

    benchmark: str = "ftse"
    aum_bn: float = 50.0

    def __post_init__(self):
        # Dates must parse and be ordered. "Outside the data range" is checked in
        # runner._load_market, where the real calendar is known.
        try:
            start = pd.Timestamp(self.start_date)
        except Exception:
            raise ValueError(f"start_date không hợp lệ: {self.start_date!r} (cần YYYY-MM-DD).")
        if self.end_date:
            try:
                end = pd.Timestamp(self.end_date)
            except Exception:
                raise ValueError(f"end_date không hợp lệ: {self.end_date!r} (cần YYYY-MM-DD).")
            if end <= start:
                raise ValueError(
                    f"end_date ({self.end_date}) phải sau start_date ({self.start_date})."
                )

        if self.cap is not None and self.universe:
            min_feasible = 1.0 / len(self.universe)
            if self.cap < min_feasible:
                raise ValueError(
                    f"cap {self.cap:.1%} quá thấp cho {len(self.universe)} mã "
                    f"(tối thiểu {min_feasible:.1%})."
                )
            # cap x max_names < 1 has no solution (long-only, sum=1): the cap_weights
            # waterfall would loop and silently return weights above the cap.
            if self.max_names and self.cap * self.max_names < 1.0 - 1e-9:
                raise ValueError(
                    f"cap {self.cap:.0%} × max_names {self.max_names} = "
                    f"{self.cap * self.max_names:.0%} < 100% — không thể phân bổ hết vốn. "
                    f"Tăng cap lên ≥ {1.0 / self.max_names:.0%} hoặc tăng max_names."
                )
