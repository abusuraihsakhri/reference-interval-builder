"""Tests for the reference interval builder's core statistics."""

import numpy as np

from refint.core import (
    CLSI_RECOMMENDED_MIN_N,
    harris_boyd_test,
    nonparametric_reference_interval,
    partition_and_compute,
    tukey_outliers,
)


def test_tukey_outliers_flags_known_extremes():
    # A clean, tight cluster with two obvious extreme values injected.
    rng = np.random.default_rng(42)
    core = rng.normal(loc=100, scale=5, size=100)
    data = np.concatenate([core, [200.0, -50.0]])

    result = tukey_outliers(data)

    assert 200.0 in result.outliers
    assert -50.0 in result.outliers
    assert 200.0 not in result.cleaned
    assert -50.0 not in result.cleaned
    # only the two injected extremes should be flagged
    assert result.outliers.size == 2
    assert result.cleaned.size == data.size - 2
    assert result.lower_fence < result.q1 < result.q3 < result.upper_fence


def test_tukey_outliers_no_outliers_in_uniform_data():
    data = list(range(1, 101))  # 1..100, no extreme values
    result = tukey_outliers(np.asarray(data, dtype=float))
    assert result.outliers.size == 0
    assert result.cleaned.size == 100


def test_nonparametric_reference_interval_matches_known_percentiles():
    # For a large, evenly spaced sample the CLSI rank formula should land
    # very close to the numpy linear-interpolation percentiles, since both
    # converge to the same result as n grows and the data has no ties.
    data = np.arange(1, 1001, dtype=float)  # 1..1000, no outliers by construction

    ri = nonparametric_reference_interval(data, label="test", ci_level=0.90)

    expected_low = np.percentile(data, 2.5)
    expected_high = np.percentile(data, 97.5)

    assert abs(ri.lower_limit - expected_low) < 2.0
    assert abs(ri.upper_limit - expected_high) < 2.0
    assert ri.lower_limit < ri.upper_limit
    # CIs should bracket the point estimate
    assert ri.lower_ci[0] <= ri.lower_limit <= ri.lower_ci[1]
    assert ri.upper_ci[0] <= ri.upper_limit <= ri.upper_ci[1]
    assert ri.n_used >= CLSI_RECOMMENDED_MIN_N
    assert not ri.below_min_n


def test_reference_interval_warns_below_clsi_minimum_n():
    data = np.linspace(50, 150, 40)  # only 40 samples, below n=120
    ri = nonparametric_reference_interval(data, label="small", ci_level=0.90)
    assert ri.n_used == 40
    assert ri.below_min_n is True


def test_reference_interval_excludes_outliers_before_computing_limits():
    rng = np.random.default_rng(7)
    core = rng.normal(loc=50, scale=3, size=150)
    contaminated = np.concatenate([core, [500.0, 500.0, 500.0]])

    with_exclusion = nonparametric_reference_interval(
        contaminated, label="with_exclusion", ci_level=0.90, exclude_outliers=True
    )
    without_exclusion = nonparametric_reference_interval(
        contaminated, label="without_exclusion", ci_level=0.90, exclude_outliers=False
    )

    # Excluding the 500.0 contaminants should pull the upper limit down
    # substantially compared to leaving them in. At least the 3 injected
    # 500.0 values must be caught (a legitimate low tail value may also
    # fall outside the recomputed fences -- that is expected Tukey behavior).
    assert with_exclusion.upper_limit < without_exclusion.upper_limit
    assert with_exclusion.n_outliers >= 3
    assert with_exclusion.outlier_values.count(500.0) == 3
    assert without_exclusion.n_outliers == 0


def test_harris_boyd_detects_clearly_different_groups():
    rng = np.random.default_rng(1)
    group_a = rng.normal(loc=100, scale=5, size=150)
    group_b = rng.normal(loc=140, scale=5, size=150)  # far away, same spread

    result = harris_boyd_test(group_a, group_b, "A", "B")

    assert result.z_statistic > result.z_critical
    assert result.partition_recommended is True


def test_harris_boyd_does_not_flag_identical_distributions():
    rng = np.random.default_rng(2)
    group_a = rng.normal(loc=100, scale=5, size=150)
    group_b = rng.normal(loc=100, scale=5, size=150)  # same distribution

    result = harris_boyd_test(group_a, group_b, "A", "B")

    assert result.z_statistic < result.z_critical
    assert result.partition_recommended is False


def test_harris_boyd_critical_value_scales_with_sample_size():
    # Same effect size and z-statistic magnitude, but a much larger n*
    # should require a higher critical value before recommending a split.
    rng = np.random.default_rng(3)
    small_a = rng.normal(loc=100, scale=10, size=20)
    small_b = rng.normal(loc=102, scale=10, size=20)
    small_result = harris_boyd_test(small_a, small_b, "A", "B")

    large_a = rng.normal(loc=100, scale=10, size=180)
    large_b = rng.normal(loc=102, scale=10, size=180)
    large_result = harris_boyd_test(large_a, large_b, "A", "B")

    assert large_result.z_critical > small_result.z_critical


def test_partition_and_compute_end_to_end():
    rng = np.random.default_rng(99)
    values_by_group = {
        "male": rng.normal(loc=14.0, scale=1.0, size=130).tolist(),
        "female": rng.normal(loc=12.5, scale=1.0, size=130).tolist(),
    }

    analysis = partition_and_compute(values_by_group, ci_level=0.90)

    assert analysis.overall.n_total == 260
    assert set(analysis.subgroups.keys()) == {"male", "female"}
    assert len(analysis.harris_boyd_pairs) == 1

    pair = analysis.harris_boyd_pairs[0]
    # These groups are 1.5 SD apart with large n; partitioning should be flagged.
    assert pair.partition_recommended is True


if __name__ == "__main__":
    import sys
    import traceback

    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
        except AssertionError:
            failures += 1
            print(f"FAIL: {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)
