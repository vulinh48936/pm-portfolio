"""Extensible feature store; today it only serves prices.

Registering another provider in FEATURE_REGISTRY adds panels reachable through
feat.get("name") without touching the engine or the Strategy contract.

allocate() receives a `FeatureView` bounded at t-1, so no-look-ahead is structural:
feat.returns(window), feat.cov(window), feat.close(), feat.adtv(), feat.get("pe").
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

from app.data.universe_config import TICKERS_FTSE
from app.lab.lib import estimate_sigma


# FeatureView: what a strategy actually holds

class FeatureView:
    """A no-look-ahead window over the (T,N) panels at one decision point.

    Cutoff `t` is exclusive: the strategy only sees rows [0, t).
    """

    def __init__(self, rets: np.ndarray, closes: np.ndarray, t: int,
                 tickers: list[str], adtv: np.ndarray | None = None,
                 extra: dict[str, np.ndarray] | None = None):
        self._rets = rets        # (T, N) daily returns, row 0 = 0
        self._closes = closes    # (T, N) close prices
        self._t = t              # cutoff (exclusive)
        self.tickers = tickers
        self.n = len(tickers)
        self._adtv = adtv
        self._extra = extra or {}

    def returns(self, window: int | None = None) -> np.ndarray:
        """Daily returns up to t-1 (row 0 dropped); last `window` rows if given."""
        hist = self._rets[1:self._t]
        return hist[-window:] if window else hist

    def cov(self, window: int = 252, shrinkage: bool = True) -> np.ndarray:
        """Annualized covariance (Ledoit-Wolf); shrinkage=False gives the sample cov."""
        rets = self.returns(window)
        if shrinkage:
            return estimate_sigma(rets, window=len(rets))
        return np.cov(rets, rowvar=False) * 252.0

    def close(self) -> np.ndarray:
        """Latest close prices, row t-1, shape (N,)."""
        return self._closes[self._t - 1]

    def closes(self, window: int | None = None) -> np.ndarray:
        """Close panel up to t-1."""
        hist = self._closes[:self._t]
        return hist[-window:] if window else hist

    def adtv(self) -> np.ndarray:
        """ADTV per ticker in billions VND, shape (N,); zeros if not loaded."""
        return self._adtv if self._adtv is not None else np.zeros(self.n)

    def get(self, name: str, window: int | None = None) -> np.ndarray:
        """An extra registered feature; raises a clear error if it is not registered."""
        if name not in self._extra:
            avail = sorted(self._extra.keys())
            raise KeyError(
                f"Feature '{name}' chưa có. Đã đăng ký: {avail or '(chỉ price)'}. "
                f"Đăng ký provider vào FEATURE_REGISTRY để dùng."
            )
        panel = self._extra[name][:self._t]
        return panel[-window:] if window else panel


# Provider protocol and the price provider

class FeatureProvider(Protocol):
    name: str

    def panels(self, tickers: list[str], calendar: pd.DatetimeIndex) -> dict[str, np.ndarray]:
        """Return {feature_name: (T,N) ndarray} aligned to the calendar."""
        ...


class PriceFeatureProvider:
    """Core provider: close, returns and ADTV from the CSV snapshot."""

    name = "price"

    def load_panel(self, tickers: list[str] = TICKERS_FTSE, start: str | None = None,
                   end: str | None = None):
        """Return (calendar, closes_arr, rets_arr, adtv_vec) for the universe.

        NaNs are kept for tickers not yet listed; the engine masks them. `start` pulls
        extra history for the optimizer warm-up. `end` freezes ADTV at the backtest end
        date but does NOT trim the price panel: runner does that, because `vis` is
        computed on the extended calendar.
        """
        from app.services.csv_data import load_closes_full, get_real_adtv

        closes_df = (load_closes_full(tickers, start=start) if start
                     else load_closes_full(tickers))
        calendar = pd.DatetimeIndex(closes_df.index)
        closes_arr = closes_df.values.astype(float)
        rets_arr = np.full_like(closes_arr, np.nan)
        rets_arr[1:] = closes_arr[1:] / closes_arr[:-1] - 1.0
        adtv_map = get_real_adtv(tickers=tickers, as_of=end)
        adtv_vec = np.array([adtv_map.get(t, 0.0) for t in tickers])
        return calendar, closes_arr, rets_arr, adtv_vec


# Extra providers beyond price. Empty for now, e.g.
# FEATURE_REGISTRY["fundamental"] = FundamentalProvider()

FEATURE_REGISTRY: dict[str, FeatureProvider] = {}


def build_extra_panels(tickers: list[str], calendar: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    """Collect panels from every registered provider, for FeatureView.get."""
    extra: dict[str, np.ndarray] = {}
    for provider in FEATURE_REGISTRY.values():
        extra.update(provider.panels(tickers, calendar))
    return extra
