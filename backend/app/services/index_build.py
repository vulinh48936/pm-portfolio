"""Build the two benchmark files from the per-ticker snapshot, after each data sync.

The basket and its column order come from `universe_config.TICKERS_FTSE`.

  build_ftse_index() -> index_ftse.csv    (date, {T}_w, {T}_ret, index_ret), drift method
  build_vnindex()    -> index_vnindex.csv (date, close, vnindex_ret)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app import paths
from app.data.universe_config import TICKERS_FTSE

DATA_DIR: Path = paths.DATA_DIR
WEIGHT_JSON: Path = paths.WEIGHT_JSON
START = "2020-01-02"


def _load_returns(tickers: list[str]) -> pd.DataFrame:
    frames = []
    for t in tickers:
        p = DATA_DIR / f"{t}.csv"
        if not p.exists():
            frames.append(pd.Series(dtype=float, name=t))
            continue
        df = pd.read_csv(p, parse_dates=["time"]).drop_duplicates(subset="time", keep="last")
        frames.append(df.set_index("time")["close"].rename(t))
    closes = pd.concat(frames, axis=1).sort_index()
    closes = closes[~closes.index.duplicated(keep="last")]
    rets = closes.pct_change(fill_method=None)
    return rets[rets.index >= pd.Timestamp(START)][tickers]


def _load_targets(tickers: list[str]) -> tuple[list[str], dict[str, np.ndarray]]:
    periods = json.loads(WEIGHT_JSON.read_text(encoding="utf-8"))["periods"]
    seen: dict[str, dict] = {}
    for p in periods:
        seen[p["effective_date"]] = p                       # last wins (Weight-Only)
    eff = sorted(seen)

    def parse(period: dict) -> np.ndarray:
        raw = {c["ticker"].replace("◆", "").strip(): c["weight_pct"] / 100.0
               for c in period["constituents"]}
        w = np.array([raw.get(t, 0.0) for t in tickers])
        s = w.sum()
        return w / s if s > 0 else w

    return eff, {d: parse(seen[d]) for d in eff}


def build_ftse_index(tickers: list[str] | None = None, write: bool = True) -> dict[str, Any]:
    tickers = list(tickers or TICKERS_FTSE)
    rets = _load_returns(tickers)
    cal = rets.index
    T, N = len(cal), len(tickers)
    if T == 0:
        raise RuntimeError("Không có return nào từ 2020-01-02 — CSV trống?")
    eff_dates, targets = _load_targets(tickers)

    avail = np.zeros((T, N), dtype=bool)
    for i, t in enumerate(tickers):
        fv = rets[t].first_valid_index()
        if fv is not None:
            avail[cal >= fv, i] = True
    ret_arr = np.where(avail, np.nan_to_num(rets.values, nan=0.0), 0.0)

    def target_for(d: pd.Timestamp) -> np.ndarray:
        ds = d.strftime("%Y-%m-%d")
        valid = [x for x in eff_dates if x <= ds]
        return targets[valid[-1] if valid else eff_dates[0]]

    y0, y1 = cal[0].year, cal[-1].year + 1
    review = sorted({f"{y}-03-01" for y in range(y0, y1)} |
                    {f"{y}-09-01" for y in range(y0, y1)} | set(eff_dates))
    rebal: set[int] = {0}
    for d in review:
        pos = int(cal.searchsorted(pd.Timestamp(d)))
        if pos < T:
            rebal.add(pos)
    for t in range(1, T):
        if not np.array_equal(avail[t], avail[t - 1]):
            rebal.add(t)

    w_tv = np.zeros((T, N))
    index_ret = np.zeros(T)
    w = None
    for t in range(T):
        if t in rebal or w is None:
            tgt = target_for(cal[t]) * avail[t]
            s = tgt.sum()
            w = tgt / s if s > 0 else avail[t] / max(avail[t].sum(), 1)
        w_tv[t] = w
        index_ret[t] = float(w @ ret_arr[t])
        if t < T - 1:
            g = w * (1.0 + ret_arr[t])
            gs = g.sum()
            if gs > 0:
                w = g / gs

    cols: dict[str, np.ndarray] = {}
    for i, t in enumerate(tickers):
        cols[f"{t}_w"] = w_tv[:, i]
        cols[f"{t}_ret"] = ret_arr[:, i]
    cols["index_ret"] = index_ret
    out = pd.DataFrame(cols, index=cal)
    out.index.name = "date"
    if write:
        path = DATA_DIR / "index_ftse.csv"
        tmp = path.with_suffix(".csv.tmp")
        out.to_csv(tmp, float_format="%.6f")
        tmp.replace(path)
    return {"rows": T, "start": str(cal[0].date()), "end": str(cal[-1].date()),
            "n_rebal": len(rebal), "ann_ret": float(index_ret.mean() * 252)}


def build_vnindex(write: bool = True) -> dict[str, Any]:
    """Derive index_vnindex.csv from `_VNINDEX_raw.csv` written by market_api."""
    raw = paths.VNINDEX_RAW_CSV
    if not raw.exists():
        raise RuntimeError("Chưa có _VNINDEX_raw.csv — chạy market_api.sync_vnindex() trước.")
    df = pd.read_csv(raw, parse_dates=["time"])[["time", "close"]].rename(columns={"time": "date"})
    df = df.drop_duplicates(subset="date", keep="last").sort_values("date")
    df = df[df["date"] >= pd.Timestamp(START)].reset_index(drop=True)
    df["vnindex_ret"] = df["close"].astype(float).pct_change().fillna(0.0)
    if write:
        path = DATA_DIR / "index_vnindex.csv"
        tmp = path.with_suffix(".csv.tmp")
        df.to_csv(tmp, index=False, float_format="%.6f")
        tmp.replace(path)
    return {"rows": len(df), "start": str(df["date"].iloc[0].date()) if len(df) else None,
            "end": str(df["date"].iloc[-1].date()) if len(df) else None}


def invalidate_caches() -> None:
    """Drop every module-level cache after the data changes, instead of restarting."""
    from app.services import csv_data
    from app.lab import service, benchmark

    csv_data.clear_cache()
    service._CACHE.clear()
    benchmark._periods_cache = None
