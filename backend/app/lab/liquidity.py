"""Liquidity flow-stress for a base portfolio.

Client flow (redemptions, subscriptions, rebalance trades) against each ticker's
liquidity. The basket bottleneck is L = min(liq_mean20 / w); every event is capped by it.

Liquidity per session is the 20-session average; slippage follows a square-root law
sigma * sqrt(Q/V); a crash multiplies impact rather than draining volume.
"""

from __future__ import annotations

import math
from typing import Any

from app.lab.config import LabConfig

_LOCK_LIQ_BN = 5.0    # below 5bn per session: flag lock risk (cannot exit on limit-down)
_AUM_SWEEP = [50, 100, 200, 500, 1000, 2000, 5000]


def capacity_summary(weights: dict[str, float], tickers: list[str], aum: float,
                     participation: float = 20.0, window: int = 252,
                     as_of: str | None = None) -> dict[str, Any]:
    """Bottleneck summary for Compare: L, the binding ticker, and the daily flow the
    book absorbs at `aum`. `as_of` measures liquidity at the backtest end, not today.
    """
    from app.services.csv_data import get_liquidity_profile

    prof = get_liquidity_profile(tickers, window=window, as_of=as_of)
    held = {t: w for t, w in weights.items() if w > 0 and t in prof}
    if not held:
        return {"bottleneck_L": 0.0, "binding_ticker": None, "max_redeem_pct": 0.0}
    ratios = {t: prof[t]["liq_mean20"] / w for t, w in held.items()}
    binding = min(ratios, key=ratios.get)
    L = ratios[binding]
    p = participation / 100.0
    return {
        "bottleneck_L": round(L, 2),
        "binding_ticker": binding,
        "max_redeem_pct": round(p * L / aum * 100, 2) if aum > 0 else 0.0,
    }


def _slippage(req_bn: float, prof: dict) -> float:
    """Estimated slippage % on a normal day, sigma * sqrt(Q/V)."""
    V = prof["liq_mean20"]
    if V <= 0 or req_bn <= 0:
        return 0.0
    return round(prof["sigma"] * math.sqrt(req_bn / V) * 100, 3)


def _event_rows(required: dict[str, float], weights: dict[str, float],
                aum: float, prof: dict[str, dict], p: float,
                extra: dict[str, dict] | None = None) -> list[dict]:
    """Per-ticker rows for one flow event; `required` is {ticker: billions to trade}.

    Each row carries slippage for a normal day and for a crash day. `extra` merges in
    per-ticker fields, used by the rebalance tab for previous/new/delta weights.
    """
    rows = []
    for t, req in required.items():
        d = prof.get(t)
        if not d:
            continue
        avail = d["liq_mean20"] * p
        shortfall = max(0.0, req - avail)
        slip = _slippage(req, d)
        row = {
            "ticker": t,
            "weight_pct": round(weights.get(t, 0.0) * 100, 2),
            "position_bn": round(aum * weights.get(t, 0.0), 2),
            "required_bn": round(req, 2),
            "available_bn": round(avail, 2),
            "shortfall_pct": round(shortfall / req * 100, 1) if req > 0 else 0.0,
            "spill_days": math.ceil(req / avail) if avail > 0 else 999,
            "slippage_pct": slip,
            "slippage_crash_pct": round(slip * d["crash_impact_mult"], 3),
        }
        if extra and t in extra:
            row.update(extra[t])
        rows.append(row)
    rows.sort(key=lambda r: (-r["shortfall_pct"], -r["slippage_crash_pct"]))
    return rows


def analyze(weights: dict[str, float], w_matrix: list[list[float]], rebal_idx: list[int],
            tickers: list[str], config: LabConfig, target_aum: float,
            redeem_pct: float = 10.0,
            participation: float = 20.0, window: int = 252,
            dates: list[str] | None = None) -> dict[str, Any]:
    """Full flow-stress analysis; percentages are passed as 0-100."""
    from app.services.csv_data import get_liquidity_profile

    p = participation / 100.0
    prof = get_liquidity_profile(tickers, window=window, as_of=config.end_date)
    held = {t: w for t, w in weights.items() if w > 0 and t in prof}
    if not held:
        return {"error": "Không có mã thanh khoản hợp lệ."}

    # Bottleneck L = min(liq_mean20 / w)
    ratios = {t: prof[t]["liq_mean20"] / w for t, w in held.items()}
    binding = min(ratios, key=ratios.get)
    L = ratios[binding]
    max_redeem = round(p * L / target_aum * 100, 2) if target_aum > 0 else 0.0

    # Curve: daily flow absorbed, by AUM
    curve = [{"aum_bn": a, "max_redeem_pct": round(p * L / a * 100, 2)} for a in _AUM_SWEEP]

    # Subscriptions are symmetric with redemptions (same volume cap), so this is
    # computed once and the UI calls it "daily flow".
    redeem_req = {t: redeem_pct / 100.0 * target_aum * w for t, w in held.items()}

    # Rebalance deltas from the most recent rebalance
    rebalance_req: dict[str, float] = {}
    rebal_meta: dict[str, dict] = {}
    rebalance_date: str | None = None
    if rebal_idx and w_matrix:
        last = max(rebal_idx)
        if 0 < last < len(w_matrix):
            prev, cur = w_matrix[last - 1], w_matrix[last]
            rebalance_req = {tickers[i]: abs(cur[i] - prev[i]) * target_aum
                             for i in range(len(tickers)) if tickers[i] in held}
            rebal_meta = {tickers[i]: {"weight_prev_pct": round(prev[i] * 100, 2),
                                       "weight_new_pct": round(cur[i] * 100, 2),
                                       "delta_pct": round((cur[i] - prev[i]) * 100, 2)}
                          for i in range(len(tickers)) if tickers[i] in held}
            if dates and last < len(dates):
                rebalance_date = dates[last]

    per_event = {
        "redeem": _event_rows(redeem_req, held, target_aum, prof, p),
        "rebalance": _event_rows(rebalance_req, held, target_aum, prof, p, extra=rebal_meta),
    }

    lock_flags = [
        {"ticker": t, "liq_bn": prof[t]["liq_mean20"],
         "reason": f"thanh khoản rất thấp ({prof[t]['liq_mean20']} tỷ/phiên) — rủi ro sàn không thoát được"}
        for t in held if prof[t]["liq_mean20"] < _LOCK_LIQ_BN
    ]

    # How much mean ADTV overstates the median, a caveat on using ADTV at all
    infl = [prof[t]["liq_mean"] / prof[t]["liq_p50"] for t in held if prof[t]["liq_p50"] > 0]
    adtv_inflation = round(sum(infl) / len(infl), 2) if infl else 1.0

    return {
        "target_aum": target_aum,
        "participation_pct": participation,
        "window": window,
        "bottleneck_L": round(L, 2),
        "binding_ticker": binding,
        "max_redeem_pct": max_redeem,      # symmetric: also the cap for subscriptions
        "capacity_curve": curve,
        "rebalance_date": rebalance_date,
        "per_event": per_event,
        "lock_flags": lock_flags,
        "adtv_inflation": adtv_inflation,
        "short_history": [t for t in held if prof[t]["short_history"]],
    }
