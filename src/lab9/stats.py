"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence
import math

import numpy as np
from scipy.stats import bootstrap

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        if h == j == "FAIL":
            cm["tp"] += 1
        elif h == "PASS" and j == "FAIL":
            cm["fp"] += 1
        elif h == "FAIL" and j == "PASS":
            cm["fn"] += 1
        elif h == j == "PASS":
            cm["tn"] += 1
        else:
            raise ValueError(f"invalid label pair: human={h!r}, judge={j!r}")
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    r = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    n = len(human)
    if n == 0 or len(judge) != n:
        raise ValueError("human and judge must be non-empty and equally long")
    cm = confusion(human, judge)
    p_observed = (cm["tp"] + cm["tn"]) / n
    p_human_fail = (cm["tp"] + cm["fn"]) / n
    p_judge_fail = (cm["tp"] + cm["fp"]) / n
    p_human_pass = 1.0 - p_human_fail
    p_judge_pass = 1.0 - p_judge_fail
    p_expected = p_human_fail * p_judge_fail + p_human_pass * p_judge_pass
    if p_expected == 1.0:
        raise ValueError("kappa is undefined for a constant judge")
    return (p_observed - p_expected) / (1.0 - p_expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denominator = sensitivity + specificity - 1.0
    if denominator == 0.0:
        raise ValueError("rogan-gladen is undefined when sensitivity + specificity == 1")
    return min(1.0, max(0.0, (observed_rate + specificity - 1.0) / denominator))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    values_a = np.asarray(a, dtype=float)
    values_b = np.asarray(b, dtype=float)
    if values_a.shape != values_b.shape or values_a.ndim != 1 or values_a.size == 0:
        raise ValueError("paired samples must be non-empty and have the same shape")
    if np.array_equal(values_a, values_b):
        return 0.0, 0.0, 0.0
    result = bootstrap(
        (values_a, values_b),
        lambda x, y, axis=-1: np.mean(x - y, axis=axis),
        paired=True,
        n_resamples=n_resamples,
        method="percentile",
        confidence_level=confidence,
        rng=np.random.default_rng(rng),
    )
    interval = result.confidence_interval
    return float(np.mean(values_a - values_b)), float(interval.low), float(interval.high)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _validate_pass_k_args(n, c, k)
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _validate_pass_k_args(n, c, k)
    return math.comb(c, k) / math.comb(n, k)


def _validate_pass_k_args(n: int, c: int, k: int) -> None:
    if n < 0 or c < 0 or c > n or k <= 0 or k > n:
        raise ValueError("need 0 <= c <= n, 1 <= k <= n")
