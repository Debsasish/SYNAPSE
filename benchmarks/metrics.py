"""Evaluation metrics with proper statistics.

Includes ranking metrics (precision@k, recall@k, MRR), calibration (Expected
Calibration Error), grounded-miss correctness, bootstrap confidence intervals,
and an ordinary-least-squares slope test used to *quantify* scale invariance:
we regress a metric on log10(T) and test whether the slope is statistically
distinguishable from zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats


# --- ranking metrics -----------------------------------------------------
def precision_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    topk = ranked[:k]
    if not topk:
        return 0.0
    hits = sum(1 for r in topk if r in gold)
    return hits / min(k, len(topk))


def hit_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    return 1.0 if any(r in gold for r in ranked[:k]) else 0.0


def recall_at_k(ranked: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return 0.0
    topk = set(ranked[:k])
    return len(topk & gold) / len(gold)


def reciprocal_rank(ranked: list[str], gold: set[str]) -> float:
    for i, r in enumerate(ranked, start=1):
        if r in gold:
            return 1.0 / i
    return 0.0


# --- calibration ---------------------------------------------------------
def expected_calibration_error(confidences: list[float], correct: list[bool], n_bins: int = 10) -> float:
    """ECE: |accuracy - confidence| averaged over confidence bins."""
    if not confidences:
        return 0.0
    conf = np.asarray(confidences, dtype=float)
    acc = np.asarray(correct, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(conf)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        if mask.sum() == 0:
            continue
        bin_conf = conf[mask].mean()
        bin_acc = acc[mask].mean()
        ece += (mask.sum() / n) * abs(bin_acc - bin_conf)
    return float(ece)


def reliability_bins(confidences: list[float], correct: list[bool], n_bins: int = 10):
    conf = np.asarray(confidences, dtype=float)
    acc = np.asarray(correct, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    centers, accs, confs, counts = [], [], [], []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        centers.append((lo + hi) / 2)
        if mask.sum() == 0:
            accs.append(np.nan); confs.append(np.nan); counts.append(0)
        else:
            accs.append(float(acc[mask].mean()))
            confs.append(float(conf[mask].mean()))
            counts.append(int(mask.sum()))
    return centers, accs, confs, counts


# --- uncertainty ---------------------------------------------------------
@dataclass
class Estimate:
    mean: float
    lo: float
    hi: float

    def __repr__(self):
        return f"{self.mean:.4f} [{self.lo:.4f}, {self.hi:.4f}]"


def bootstrap_ci(values, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> Estimate:
    """Percentile bootstrap 95% CI of the mean."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return Estimate(float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    n = arr.size
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        means[b] = arr[idx].mean()
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return Estimate(float(arr.mean()), lo, hi)


# --- scale-invariance test ----------------------------------------------
@dataclass
class SlopeTest:
    slope: float
    intercept: float
    ci_lo: float
    ci_hi: float
    p_value: float
    r_squared: float
    flat: bool          # True if slope CI includes 0 (i.e. indistinguishable from flat)

    def __repr__(self):
        return (f"slope={self.slope:.4g} 95%CI[{self.ci_lo:.4g},{self.ci_hi:.4g}] "
                f"p={self.p_value:.3g} R2={self.r_squared:.3f} flat={self.flat}")


def slope_vs_logT(T_values, metric_values, alpha: float = 0.05) -> SlopeTest:
    """OLS regression of ``metric`` on log10(T).

    A metric is 'scale-invariant' if the slope's confidence interval includes 0.
    A metric is 'scaling' (e.g. MCP context) if the slope is significantly != 0.
    """
    x = np.log10(np.asarray(T_values, dtype=float))
    return _ols(x, np.asarray(metric_values, dtype=float), alpha)


def slope_vs_T(T_values, metric_values, alpha: float = 0.05) -> SlopeTest:
    """OLS regression of ``metric`` on raw T (correct model for O(T) growth).

    MCP context/cost grow *linearly in T*; regressing on T (not log T) is the
    correctly specified test and yields R^2 ~ 1 for a truly linear cost.
    """
    x = np.asarray(T_values, dtype=float)
    return _ols(x, np.asarray(metric_values, dtype=float), alpha)


def _ols(x, y, alpha: float) -> SlopeTest:
    res = stats.linregress(x, y)
    n = len(x)
    if n > 2 and not math.isnan(res.stderr):
        tcrit = stats.t.ppf(1 - alpha / 2, df=n - 2)
        lo = res.slope - tcrit * res.stderr
        hi = res.slope + tcrit * res.stderr
    else:
        lo = hi = res.slope
    flat = (lo <= 0.0 <= hi)
    return SlopeTest(
        slope=float(res.slope),
        intercept=float(res.intercept),
        ci_lo=float(lo),
        ci_hi=float(hi),
        p_value=float(res.pvalue),
        r_squared=float(res.rvalue ** 2),
        flat=bool(flat),
    )


def cohens_d(a, b) -> float:
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    va, vb = a.var(ddof=1), b.var(ddof=1)
    pooled = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)
