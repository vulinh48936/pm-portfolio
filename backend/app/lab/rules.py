"""Hard rules applied after strategy.allocate, so a strategy cannot bypass them.

Order: zero out tickers under the ADTV floor, keep the top max_names, renormalize.
The engine applies cap_weights last. min_names only warns.
"""

from __future__ import annotations

import numpy as np

from app.lab.config import LabConfig


def apply_hard_rules(w: np.ndarray, config: LabConfig,
                     adtv: np.ndarray | None) -> np.ndarray:
    """Apply the ADTV floor and max_names to pre-cap target weights."""
    w = np.clip(np.asarray(w, dtype=float), 0.0, None)

    if config.adtv_floor_bn and adtv is not None:
        w = np.where(adtv >= config.adtv_floor_bn, w, 0.0)

    if config.max_names and int((w > 0).sum()) > config.max_names:
        keep = np.argsort(w)[::-1][:config.max_names]
        mask = np.zeros_like(w, dtype=bool)
        mask[keep] = True
        w = np.where(mask, w, 0.0)

    s = w.sum()
    return w / s if s > 0 else w


def rule_warnings(weights: dict[str, float], config: LabConfig,
                  adtv_map: dict[str, float]) -> list[str]:
    """Warnings about the final weights (min_names, tickers below the ADTV floor)."""
    held = [t for t, x in weights.items() if x > 0]
    out: list[str] = []
    if config.min_names and len(held) < config.min_names:
        out.append(f"Chỉ {len(held)} mã có weight > 0, dưới min_names = {config.min_names}.")
    if config.adtv_floor_bn:
        low = [t for t in held if adtv_map.get(t, 0.0) < config.adtv_floor_bn]
        if low:
            out.append(f"{len(low)} mã dưới ADTV floor {config.adtv_floor_bn} tỷ đã bị loại: {', '.join(low[:5])}")
    return out
