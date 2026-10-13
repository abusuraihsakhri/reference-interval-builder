"""Regression tests for statistical validation, signed audit trails and batch I/O."""
import csv
import math

import pytest

from agents.base import AuditTrail
from cli import main as agent_main
from refint.core import harris_boyd_test, nonparametric_reference_interval, partition_and_compute, tukey_outliers
from reference_interval_builder import read_csv_column


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_reference_interval_rejects_nonfinite_data(bad):
    with pytest.raises(ValueError, match="NaN or infinite"):
        nonparametric_reference_interval([1, 2, bad])


@pytest.mark.parametrize("ci", [math.nan, math.inf, 0.0, 1.0, -0.5])
def test_reference_interval_rejects_bad_confidence_levels(ci):
    with pytest.raises(ValueError, match="ci_level"):
        nonparametric_reference_interval([1, 2, 3], ci_level=ci)


def test_outlier_fence_multiplier_validation():
    with pytest.raises(ValueError, match="multiplier"):
        tukey_outliers([1, 2, 3], k=-1)


def test_empty_partition_input_is_actionable():
    with pytest.raises(ValueError, match="at least one group"):
        partition_and_compute({})


def test_harris_boyd_constant_distinct_groups():
    res = harris_boyd_test([10, 10, 10], [20, 20, 20], "A", "B")
    assert math.isinf(res.z_statistic)
    assert res.partition_recommended
    assert harris_boyd_test([5, 5], [5, 5], "A", "B").z_statistic == 0


def test_audit_detects_signed_field_tampering():
    audit = AuditTrail("unit-test-only-secret")
    audit.log("actor", "tier", "CREATE", {"outcome": "ok"})
    audit.log("actor", "tier", "CHECK", {"outcome": "ok"})
    assert audit.verify_integrity()
    audit.logs[0]["actor"] = "forged"
    assert not audit.verify_integrity()


def test_audit_trail_return_value_cannot_modify_internal_history():
    audit = AuditTrail("unit-test-only-secret")
    audit.log("actor", "tier", "CREATE", {"outcome": "ok"})
    copy = audit.get_trail()
    copy[0]["event_type"] = "FORGED"
    assert audit.verify_integrity()
    assert audit.get_trail()[0]["event_type"] == "CREATE"


def test_csv_reader_skips_nonfinite_observations(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text("lab,sex\n5,F\nNaN,F\ninf,M\n6,M\n", encoding="utf8")
    assert read_csv_column(str(source), "lab", "sex") == {"F": [5.0], "M": [6.0]}


def test_agent_batch_false_flag_is_not_treated_as_true(tmp_path):
    source = tmp_path / "tasks.csv"
    destination = tmp_path / "output.csv"
    source.write_text(
        "task_id,target_identifier,primary_metric,secondary_metric,status_descriptor,is_critical_flag\n"
        "CASE-01,KEY-01,10,1,NOMINAL,False\n"
        "CASE-02,KEY-02,10,1,NOMINAL,True\n",
        encoding="utf8",
    )
    assert agent_main(["batch", "--input", str(source), "--output", str(destination)]) == 0
    with destination.open(newline="", encoding="utf8") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["overall_urgency"] == "ROUTINE"
    assert rows[1]["overall_urgency"] == "CRITICAL_STAT_PANIC"
