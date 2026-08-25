"""Reference Interval Builder

Computes clinical reference intervals from healthy-subject lab data using
the CLSI EP28-A3c nonparametric percentile method.
"""

from .core import (
    ReferenceInterval,
    HarrisBoydResult,
    tukey_outliers,
    nonparametric_reference_interval,
    harris_boyd_test,
    partition_and_compute,
)

__all__ = [
    "ReferenceInterval",
    "HarrisBoydResult",
    "tukey_outliers",
    "nonparametric_reference_interval",
    "harris_boyd_test",
    "partition_and_compute",
]
