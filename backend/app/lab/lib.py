"""Allocation primitives available to generated strategy code.

    from app.lab.lib import risk_parity, min_var, factor_tilt, estimate_sigma, cap_weights
"""

from __future__ import annotations

import numpy as np
from sklearn.covariance import LedoitWolf


# Helpers

def _zscore(x: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score, safe when std is about zero."""
    mu, sd = float(np.mean(x)), float(np.std(x))
    if sd < 1e-12:
        return np.zeros_like(x)
    return (x - mu) / sd


def cap_weights(w: np.ndarray, cap: float | None, max_iter: int = 100) -> np.ndarray:
    """Cap each weight at `cap`, redistributing the excess to names below it.

    Keeps sum=1 and long-only. cap=None or >=1.0 only normalizes.
    """
    w = np.clip(np.asarray(w, dtype=float), 0.0, None)
    s = w.sum()
    if s <= 0:
        return w
    w = w / s
    if cap is None or cap >= 1.0:
        return w
    for _ in range(max_iter):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        room = (~over) & (w > 0)
        if not room.any():
            w[:] = w + excess / len(w)
            break
        w[room] += excess * (w[room] / w[room].sum())
    return w


def estimate_sigma(rets_hist: np.ndarray, window: int = 252) -> np.ndarray:
    """Annualized Ledoit-Wolf shrinkage covariance over the last `window` days."""
    w = rets_hist[-window:]
    return LedoitWolf().fit(w).covariance_ * 252.0


# Allocation methods

def factor_scores(rets_hist: np.ndarray,
                  mom_window: int = 120,
                  vol_window: int = 60) -> np.ndarray:
    """Composite score: 0.5*momentum + 0.5*low_vol (cross-sectional z-scores)."""
    mom = np.prod(1.0 + rets_hist[-mom_window:], axis=0) - 1.0
    vol = rets_hist[-vol_window:].std(axis=0) * np.sqrt(252.0)
    return 0.5 * _zscore(mom) + 0.5 * _zscore(-vol)


def factor_tilt(rets_hist: np.ndarray, w_bench: np.ndarray,
                tilt_strength: float = 1.0) -> np.ndarray:
    """w = w_bench * exp(lambda * score), normalized. Stays close to the benchmark."""
    score = factor_scores(rets_hist)
    w = w_bench * np.exp(tilt_strength * score)
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else w_bench.copy()


# Tilt primitives

def momentum_score(rets_hist: np.ndarray, window: int = 120) -> np.ndarray:
    """Z-score of momentum, the cumulative return over `window` days."""
    return _zscore(np.prod(1.0 + rets_hist[-window:], axis=0) - 1.0)


def lowvol_score(rets_hist: np.ndarray, window: int = 60) -> np.ndarray:
    """Z-score of -volatility, so low vol scores high."""
    return _zscore(-rets_hist[-window:].std(axis=0))


def downvol_score(rets_hist: np.ndarray, window: int = 120) -> np.ndarray:
    """Z-score of -downside deviation: only down days are penalized."""
    x = rets_hist[-window:]
    neg = np.where(x < 0.0, x, 0.0)
    return _zscore(-np.sqrt((neg ** 2).mean(axis=0)))


def tilt(anchor: np.ndarray, score: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Multiplicative tilt: w = anchor * exp(strength * score), long-only, normalized.

    `anchor` is the base weighting (benchmark, ERC, equal); strength sets how far it tilts.
    """
    w = anchor * np.exp(strength * score)
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else anchor.copy()


def trailing_stop_gate(closes: np.ndarray, window: int = 120,
                       threshold: float = 0.15, reduce_to: float = 0.0) -> np.ndarray:
    """Per-stock trailing-loss gate returning `reduce_to` or 1.0 for each name.

    A stock more than `threshold` below its `window`-day peak gets `reduce_to`
    (0.0 cuts it entirely, 0.3 keeps 30%); others get 1.0. Multiply into the weights and
    renormalize to move capital away from falling names:

        w = w * trailing_stop_gate(feat.closes(), 120, 0.15, 0.0)
        w = w / w.sum()
    """
    cl = closes[-window:] if window else closes
    peak = cl.max(axis=0)
    trail_dd = closes[-1] / np.where(peak > 0, peak, np.nan) - 1.0
    return np.where(trail_dd <= -threshold, reduce_to, 1.0)


def efficiency_ratio(closes: np.ndarray, window: int = 20) -> np.ndarray:
    """Kaufman Efficiency Ratio per stock, in [0,1]: how clean a trend is.

    ER = |net price change over `window`| / sum of |daily changes|. A smooth trend gives
    ER near 1, a choppy or sideways path near 0. Direction-agnostic, so it works as a
    quality weight on momentum.
    """
    cl = closes[-(window + 1):]
    net = np.abs(cl[-1] - cl[0])
    path = np.abs(np.diff(cl, axis=0)).sum(axis=0)
    return np.nan_to_num(net / np.where(path > 0, path, np.nan))


def er_momentum_score(closes: np.ndarray, mom_window: int = 120,
                      er_window: int = 20, floor: float = 0.5) -> np.ndarray:
    """Z-score of momentum weighted by the Efficiency Ratio: quality momentum.

    Raw momentum over `mom_window` is scaled by (floor + (1-floor) * ER). A stock that
    rose on a smooth trend keeps its momentum; one that rose on a few jumpy sessions is
    discounted towards `floor`, which filters momentum that is mostly noise.
    """
    mom = closes[-1] / closes[-(mom_window + 1)] - 1.0
    er = efficiency_ratio(closes, er_window)
    return _zscore(mom * (floor + (1.0 - floor) * er))


def liquidity_score(adtv: np.ndarray) -> np.ndarray:
    """Z-score of log(1+ADTV): liquid names score high, tilting towards tradability."""
    return _zscore(np.log1p(adtv))


def liq_share_cap(w: np.ndarray, adtv: np.ndarray, lam: float = 7.0,
                  floor: float = 0.005) -> np.ndarray:
    """Cap weights by each name's share of universe liquidity, independent of AUM.

    cap_i = max(floor, lam * ADTV_i / sum(ADTV)), with a waterfall for the excess. Where
    the cap binds, weight is proportional to ADTV, so the trade each name needs scales
    with its own liquidity and no single name becomes the bottleneck at any AUM.

    If the caps of the held names sum below 1 (for example after a trailing gate cuts
    most of the basket), the caps are scaled up so the overflow goes to the most liquid
    names instead of piling into one average one. Lower `lam` caps harder, trading
    return for capacity; about 7 measured well.
    """
    w = np.clip(np.asarray(w, dtype=float), 0.0, None)
    s = w.sum()
    if s <= 0:
        return w
    w = w / s
    tot = float(adtv.sum())
    if tot <= 0:
        return w
    caps = np.clip(lam * adtv / tot, floor, 1.0)
    alive = w > 0
    capsum = float(caps[alive].sum())
    if 0.0 < capsum < 1.0:
        caps = caps / capsum
    for _ in range(100):
        over = w > caps + 1e-12
        if not over.any():
            break
        excess = float((w[over] - caps[over]).sum())
        w[over] = caps[over]
        room = (~over) & (w > 0)
        if not room.any():
            break
        w[room] += excess * (w[room] / w[room].sum())
    s = w.sum()
    return w / s if s > 0 else w


def lowbeta_score(rets_hist: np.ndarray, window: int = 120) -> np.ndarray:
    """Z-score of -beta against an equal-weight market: betting against beta."""
    x = rets_hist[-window:]
    mkt = x.mean(axis=1)
    var = float(mkt.var()) + 1e-12
    beta = np.array([np.cov(x[:, i], mkt)[0, 1] / var for i in range(x.shape[1])])
    return _zscore(-beta)


def downside_cov(rets_hist: np.ndarray, window: int = 252) -> np.ndarray:
    """Annualized semi-covariance, built from negative returns only.

    Feed it to min_var or risk_parity to optimize downside risk without penalizing
    upside volatility.
    """
    x = rets_hist[-window:]
    d = np.minimum(x, 0.0)
    return (d.T @ d) / len(d) * 252.0


def min_var(rets_hist: np.ndarray | None = None, Sigma: np.ndarray | None = None,
            cap: float = 1.0) -> np.ndarray:
    """Long-only minimum variance: min w'Sw subject to sum=1 and 0<=w<=cap (SLSQP)."""
    import scipy.optimize as opt
    if Sigma is None:
        Sigma = estimate_sigma(rets_hist)
    n = Sigma.shape[0]

    res = opt.minimize(
        lambda w: float(w @ Sigma @ w), np.ones(n) / n,
        jac=lambda w: 2.0 * (Sigma @ w), method='SLSQP',
        bounds=[(0.0, cap)] * n,
        constraints=[{'type': 'eq', 'fun': lambda w: w.sum() - 1.0}],
        options={'ftol': 1e-10, 'maxiter': 300},
    )
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else np.ones(n) / n


def risk_parity(rets_hist: np.ndarray | None = None, Sigma: np.ndarray | None = None,
                iters: int = 1000) -> np.ndarray:
    """Equal risk contribution, long-only, by fixed-point iteration.

    Every name ends with the same RC_i = w_i * (Sw)_i.
    """
    if Sigma is None:
        Sigma = estimate_sigma(rets_hist)
    n = Sigma.shape[0]
    w = 1.0 / np.sqrt(np.diag(Sigma) + 1e-12)
    w = w / w.sum()
    for _ in range(iters):
        rc = w * (Sigma @ w)
        avg = float(rc.mean())
        w = np.clip(w * np.sqrt(avg / (rc + 1e-12)), 0.0, None)
        s = w.sum()
        if s > 0:
            w = w / s
    return w
