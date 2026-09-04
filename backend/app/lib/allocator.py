"""Round-lot allocation for the Vietnamese market, where one lot is 100 shares.

Used by the feasibility check. Greedy allocator, numpy only.
"""

from __future__ import annotations
import numpy as np

LOT_SIZE = 100  # VN market round-lot


def compute_lot_positions(
    aum_vnd: float,
    weights: np.ndarray,
    prices: np.ndarray,
    lot_size: int = LOT_SIZE,
) -> tuple[np.ndarray, float]:
    """Lots per stock for a given AUM, using greedy largest-shortfall.

    Floor each target to whole lots, then spend the leftover cash one lot at a time on
    whichever stock is furthest below its target.

    Args:
        aum_vnd:  total capital in VND
        weights:  target weights summing to 1, shape (N,)
        prices:   close price per share in VND, shape (N,)
        lot_size: 100 by default

    Returns:
        lots:     lots per stock, shape (N,)
        leftover: cash left uninvested, in VND
    """
    prices = np.asarray(prices, dtype=float)
    weights = np.asarray(weights, dtype=float)

    lot_price = lot_size * prices          # VND / lot
    target_vnd = weights * aum_vnd        # target value per stock, in VND

    # Floor to whole lots
    lots = np.floor(target_vnd / lot_price).astype(np.int64)
    spent = float((lots * lot_price).sum())
    cash = aum_vnd - spent

    # Greedy: add one lot to the stock with the largest shortfall
    while True:
        shortfall = target_vnd - lots * lot_price
        mask = (shortfall > 0) & (lot_price <= cash)
        if not mask.any():
            break
        i = int(np.where(mask, shortfall, -np.inf).argmax())
        lots[i] += 1
        cash -= float(lot_price[i])

    return lots, cash
