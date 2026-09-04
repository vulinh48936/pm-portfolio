"""Pydantic request and response models for the router."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.data.universe_config import TICKERS_FTSE
from app.lab.config import LabConfig


class LabConfigIn(BaseModel):
    universe: list[str] | None = None
    start_date: str = "2020-01-02"
    end_date: str | None = None
    cap: float | None = 0.25
    aum_bn: float = 50.0
    adtv_floor_bn: float | None = None
    max_names: int | None = None
    min_names: int | None = None

    def to_config(self) -> LabConfig:
        return LabConfig(
            universe=self.universe or list(TICKERS_FTSE),
            start_date=self.start_date,
            end_date=self.end_date,
            cap=self.cap,
            aum_bn=self.aum_bn,
            adtv_floor_bn=self.adtv_floor_bn,
            max_names=self.max_names,
            min_names=self.min_names,
        )


class StrategySpec(BaseModel):
    code: str | None = None
    preset: str | None = None


class GenerateIn(BaseModel):
    nl_request: str
    config: LabConfigIn = Field(default_factory=LabConfigIn)
    model: str | None = None


class BacktestIn(BaseModel):
    spec: StrategySpec
    config: LabConfigIn = Field(default_factory=LabConfigIn)


class CompareItem(BaseModel):
    name: str
    spec: StrategySpec


class CompareIn(BaseModel):
    strategies: list[CompareItem]
    config: LabConfigIn = Field(default_factory=LabConfigIn)


class WeightGridIn(BaseModel):
    strategies: list[CompareItem]
    config: LabConfigIn = Field(default_factory=LabConfigIn)
    date: str | None = None
    # Force a rebalance on the last session and show the weights after it.
    # `date` is ignored in that mode, since force only applies at end_date.
    force_rebalance: bool = False


class AttributionIn(BaseModel):
    spec: StrategySpec
    config: LabConfigIn = Field(default_factory=LabConfigIn)
    window_start: str | None = None


class ExplainIn(BaseModel):
    spec: StrategySpec
    config: LabConfigIn = Field(default_factory=LabConfigIn)
    model: str | None = None


class LiquidityIn(BaseModel):
    spec: StrategySpec
    config: LabConfigIn = Field(default_factory=LabConfigIn)
    target_aum: float | None = None       # None falls back to config.aum_bn
    redeem_pct: float = 10.0     # daily flow, used for both redemptions and subscriptions
    participation: float = 20.0
    window: int = 252


class SaveStrategyIn(BaseModel):
    name: str
    nl_prompt: str = ""
    code: str
    config: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    rebalance_schedule: str = "quarterly"
    move_policy: str = "band"


def _spec_dict(spec: StrategySpec) -> dict[str, Any]:
    return {"code": spec.code, "preset": spec.preset}


class JobRunIn(BaseModel):
    sync: bool = True                  # False skips the Data API and only re-backtests
    end: str | None = None             # YYYY-MM-DD; None follows job_data_day
    include_presets: bool = True
    include_saved: bool = True
    # Re-crawl the whole history from MARKET_HISTORY_START. Needed after a dividend or
    # split, which rewrites the adjusted series that incremental sync cannot see.
    full_sync: bool = False


class ScheduleIn(BaseModel):
    """Schedule changes; a None field is left unchanged."""
    scheduler_enabled: bool | None = None
    scheduler_time: str | None = None          # "HH:MM"
    scheduler_tz: str | None = None
    scheduler_weekdays_only: bool | None = None
    job_data_day: str | None = None            # "T" | "T-1"


class ConstituentIn(BaseModel):
    ticker: str
    weight_pct: float


class WeightPeriodIn(BaseModel):
    """One review period; an empty `period` defaults to YYYY-MM of effective_date."""
    constituents: list[ConstituentIn]
    period: str | None = None


class WeightPasteIn(BaseModel):
    text: str
