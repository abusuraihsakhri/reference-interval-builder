"""Core statistics for the Reference Interval Builder.

Implements:
  * Tukey's method for outlier exclusion (1.5 x IQR fences).
  * The CLSI EP28-A3c nonparametric rank-based percentile method for the
    2.5th / 97.5th percentile reference limits.
  * Nonparametric (rank-based) confidence intervals around those limits,
    using the normal approximation to the binomial distribution of order
    statistic rank -- the approach CLSI EP28-A3c uses for samples large
    enough that the exact rank table is impractical to reproduce here.
  * The Harris & Boyd (1990) test for whether two candidate subgroups
    (e.g. male/female, or adjacent age bands) should be reported as
    separate reference intervals rather than pooled.

CLSI recommends a minimum of n = 120 (after outlier removal) for the
nonparametric method; this module flags any group that falls short.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from scipy import stats

CLSI_RECOMMENDED_MIN_N = 120


def _finite_vector(data: Sequence[float], name: str) -> np.ndarray:
    """Require a one-dimensional series of finite observations."""
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional series")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains NaN or infinite observations")
    return arr

# z critical values for a two-sided confidence interval on a percentile rank.
_Z_FOR_CI = {
    0.80: 1.2816,
    0.90: 1.6449,
    0.95: 1.9600,
    0.99: 2.5758,
}


def _z_for_ci_level(ci_level: float) -> float:
    """Return the two-sided normal z value for the requested CI level.

    Uses the exact table for the common CLSI levels (90%/95%) and falls
    back to scipy's inverse normal CDF for anything else.
    """
    if not math.isfinite(ci_level) or not 0.5 <= ci_level < 1.0:
        raise ValueError("ci_level must be finite and in the range [0.5, 1)")
    if ci_level in _Z_FOR_CI:
        return _Z_FOR_CI[ci_level]
    return float(stats.norm.ppf(0.5 + ci_level / 2.0))


# ---------------------------------------------------------------------------
# Outlier exclusion (Tukey's method)
# ---------------------------------------------------------------------------


@dataclass
class TukeyResult:
    cleaned: np.ndarray
    outliers: np.ndarray
    lower_fence: float
    upper_fence: float
    q1: float
    q3: float


def tukey_outliers(data: Sequence[float], k: float = 1.5) -> TukeyResult:
    """Flag and remove outliers using Tukey's 1.5 x IQR fence method.

    Q1 and Q3 are the 25th/75th percentiles (linear interpolation, the
    standard numpy default). Values outside [Q1 - k*IQR, Q3 + k*IQR] are
    excluded before the reference interval is computed, per CLSI EP28-A3c's
    recommendation to screen for outliers prior to percentile estimation.
    """
    arr = _finite_vector(data, "data")
    if not math.isfinite(k) or k < 0:
        raise ValueError("Tukey fence multiplier k must be finite and nonnegative")
    if arr.size == 0:
        raise ValueError("cannot screen an empty sample for outliers")

    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    lower_fence = q1 - k * iqr
    upper_fence = q3 + k * iqr

    mask = (arr >= lower_fence) & (arr <= upper_fence)
    return TukeyResult(
        cleaned=arr[mask],
        outliers=arr[~mask],
        lower_fence=lower_fence,
        upper_fence=upper_fence,
        q1=q1,
        q3=q3,
    )


# ---------------------------------------------------------------------------
# CLSI EP28-A3c nonparametric percentile method
# ---------------------------------------------------------------------------


def _rank_position(n: int, p: float) -> float:
    """CLSI EP28-A3c nonparametric rank position for percentile p (0-1)."""
    return p * (n + 1)


def _interpolated_value(sorted_data: np.ndarray, rank: float) -> float:
    """Value at a (possibly fractional) 1-indexed rank, per CLSI EP28-A3c.

    When the rank falls between two integer ranks, the CLSI method
    interpolates linearly between the two bracketing order statistics.
    Ranks outside [1, n] are clamped to the sample min/max.
    """
    n = sorted_data.size
    if rank <= 1:
        return float(sorted_data[0])
    if rank >= n:
        return float(sorted_data[-1])

    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(sorted_data[lo - 1])

    frac = rank - lo
    lo_val = sorted_data[lo - 1]
    hi_val = sorted_data[hi - 1]
    return float(lo_val + frac * (hi_val - lo_val))


def _rank_ci(n: int, p: float, z: float) -> tuple[int, int]:
    """Nonparametric CI rank bounds for the p-th percentile's order statistic.

    Uses the normal approximation to the binomial distribution of the rank
    of the p-th percentile (se = sqrt(n*p*(1-p))), which is the standard
    large-sample nonparametric approach referenced by CLSI EP28-A3c for
    building a confidence interval around a rank-based percentile.
    """
    se = math.sqrt(n * p * (1 - p))
    lo = n * p - z * se
    hi = n * p + z * se
    lo_rank = max(1, int(round(lo)))
    hi_rank = min(n, int(round(hi)) + 1)
    if hi_rank < lo_rank:
        hi_rank = lo_rank
    return lo_rank, hi_rank


@dataclass
class ReferenceInterval:
    label: str
    n_total: int
    n_used: int
    n_outliers: int
    outlier_values: list
    lower_limit: float
    upper_limit: float
    lower_ci: tuple
    upper_ci: tuple
    ci_level: float
    below_min_n: bool = field(init=False)

    def __post_init__(self):
        self.below_min_n = self.n_used < CLSI_RECOMMENDED_MIN_N


def nonparametric_reference_interval(
    data: Sequence[float],
    label: str = "overall",
    ci_level: float = 0.90,
    exclude_outliers: bool = True,
) -> ReferenceInterval:
    """Compute a CLSI EP28-A3c nonparametric reference interval.

    Steps: optionally screen out Tukey outliers, then compute the 2.5th and
    97.5th percentiles by rank interpolation, then compute a nonparametric
    confidence interval around each limit.
    """
    arr = _finite_vector(data, label)
    _z_for_ci_level(ci_level)
    if arr.size < 2:
        raise ValueError(f"{label}: need at least 2 observations, got {arr.size}")

    n_total = arr.size
    if exclude_outliers:
        tukey = tukey_outliers(arr)
        cleaned = tukey.cleaned
        outlier_values = sorted(tukey.outliers.tolist())
    else:
        cleaned = arr
        outlier_values = []

    n_used = cleaned.size
    if n_used < 2:
        raise ValueError(
            f"{label}: fewer than 2 observations remain after outlier exclusion"
        )

    sorted_data = np.sort(cleaned)
    z = _z_for_ci_level(ci_level)

    lower_rank = _rank_position(n_used, 0.025)
    upper_rank = _rank_position(n_used, 0.975)
    lower_limit = _interpolated_value(sorted_data, lower_rank)
    upper_limit = _interpolated_value(sorted_data, upper_rank)

    lo_ci_ranks = _rank_ci(n_used, 0.025, z)
    hi_ci_ranks = _rank_ci(n_used, 0.975, z)
    lower_ci = (
        float(sorted_data[lo_ci_ranks[0] - 1]),
        float(sorted_data[lo_ci_ranks[1] - 1]),
    )
    upper_ci = (
        float(sorted_data[hi_ci_ranks[0] - 1]),
        float(sorted_data[hi_ci_ranks[1] - 1]),
    )

    return ReferenceInterval(
        label=label,
        n_total=n_total,
        n_used=n_used,
        n_outliers=n_total - n_used,
        outlier_values=outlier_values,
        lower_limit=lower_limit,
        upper_limit=upper_limit,
        lower_ci=lower_ci,
        upper_ci=upper_ci,
        ci_level=ci_level,
    )


# ---------------------------------------------------------------------------
# Harris-Boyd partitioning test
# ---------------------------------------------------------------------------

# Critical z-value table for the Harris & Boyd (1990) partitioning test,
# indexed by n* = the size of the smaller of the two candidate subgroups.
# The critical value increases with n* because larger samples make the
# z statistic more sensitive to trivial differences; without this scaling
# the test would over-partition as sample sizes grow. Values below follow
# the stepwise table reproduced in Harris & Boyd's original work and later
# summarized by Ichihara & Boyd (2010), Clin Chem Lab Med 48:1537-1551.
_HARRIS_BOYD_TABLE = (
    (25, 2.50),
    (50, 2.60),
    (75, 2.70),
    (100, 2.80),
    (150, 2.90),
    (200, 3.00),
    (float("inf"), 3.10),
)


def _harris_boyd_critical_z(n_star: int) -> float:
    for threshold, z_crit in _HARRIS_BOYD_TABLE:
        if n_star <= threshold:
            return z_crit
    return _HARRIS_BOYD_TABLE[-1][1]


@dataclass
class HarrisBoydResult:
    group_a: str
    group_b: str
    n_a: int
    n_b: int
    n_star: int
    z_statistic: float
    z_critical: float
    partition_recommended: bool


def harris_boyd_test(
    data_a: Sequence[float], data_b: Sequence[float], label_a: str, label_b: str
) -> HarrisBoydResult:
    """Test whether two subgroups warrant separate reference intervals.

    z = |mean_a - mean_b| / sqrt(var_a/n_a + var_b/n_b)

    z is compared against a critical value that scales with n* = the
    smaller subgroup size (see `_HARRIS_BOYD_TABLE`). Partitioning into
    separate reference intervals is recommended only when z exceeds the
    critical value for that sample size.
    """
    a = _finite_vector(data_a, label_a)
    b = _finite_vector(data_b, label_b)
    n_a, n_b = a.size, b.size
    if n_a < 2 or n_b < 2:
        raise ValueError("Harris-Boyd test requires at least 2 observations per group")

    mean_a, mean_b = float(np.mean(a)), float(np.mean(b))
    var_a, var_b = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))

    se = math.sqrt(var_a / n_a + var_b / n_b)
    z = abs(mean_a - mean_b) / se if se > 0 else (
        math.inf if mean_a != mean_b else 0.0
    )

    n_star = min(n_a, n_b)
    z_crit = _harris_boyd_critical_z(n_star)

    return HarrisBoydResult(
        group_a=label_a,
        group_b=label_b,
        n_a=n_a,
        n_b=n_b,
        n_star=n_star,
        z_statistic=z,
        z_critical=z_crit,
        partition_recommended=z > z_crit,
    )


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------


@dataclass
class PartitionAnalysis:
    overall: ReferenceInterval
    subgroups: dict
    harris_boyd_pairs: list


def partition_and_compute(
    values_by_group: dict, ci_level: float = 0.90
) -> PartitionAnalysis:
    """Compute the overall RI, per-subgroup RIs, and pairwise Harris-Boyd tests.

    `values_by_group` maps group label -> sequence of numeric lab values.
    """
    if not values_by_group:
        raise ValueError("at least one group is required")
    validated = {
        label: _finite_vector(values, str(label))
        for label, values in values_by_group.items()
    }
    all_values = np.concatenate(list(validated.values()))
    overall = nonparametric_reference_interval(all_values, "overall", ci_level)

    subgroups = {
        label: nonparametric_reference_interval(vals, label, ci_level)
        for label, vals in validated.items()
    }

    labels = list(validated.keys())
    pairs = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            la, lb = labels[i], labels[j]
            pairs.append(
                harris_boyd_test(validated[la], validated[lb], la, lb)
            )

    return PartitionAnalysis(overall=overall, subgroups=subgroups, harris_boyd_pairs=pairs)
