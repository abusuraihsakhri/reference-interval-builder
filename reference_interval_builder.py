#!/usr/bin/env python3
"""Reference Interval Builder -- CLSI EP28-A3c nonparametric CLI.

Computes clinical reference intervals from a sample of healthy-subject lab
results using the CLSI EP28-A3c nonparametric percentile method, with Tukey
outlier exclusion, rank-based confidence intervals, and the Harris-Boyd test
for whether age/sex partitioning is statistically warranted.

Example:
    python reference_interval_builder.py --input sample_data.csv \
        --value-column glucose --group-column sex --ci 0.90
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from io import StringIO
from pathlib import Path

from refint.core import (
    CLSI_RECOMMENDED_MIN_N,
    HarrisBoydResult,
    PartitionAnalysis,
    ReferenceInterval,
    nonparametric_reference_interval,
    partition_and_compute,
)


def _safe_resolve_path(path_str: str) -> Path:
    """Reject traversal syntax, symlinks, and non-regular input paths.

    Explicit absolute regular-file paths remain supported.
    """
    original = Path(path_str)
    if original.is_symlink():
        raise ValueError("symlinked input files are not permitted")
    path = original.resolve()
    if ".." in Path(path_str).parts:
        raise ValueError(
            f"path '{path_str}' contains '..' traversal components; "
            f"provide a path within the working directory"
        )
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if not path.is_file():
        raise ValueError(f"path '{path}' is not a regular file")
    return path


def read_csv_column(
    path: str, value_column: str, group_column: str | None
) -> dict:
    """Read a CSV file and return {group_label: [values]}.

    If group_column is None, every row is placed under the single key
    "overall". Rows with a non-numeric or missing value are skipped.
    """
    groups: dict = defaultdict(list)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if value_column not in (reader.fieldnames or []):
            raise ValueError(
                f"column '{value_column}' not found in {path}; "
                f"available columns: {reader.fieldnames}"
            )
        if group_column and group_column not in (reader.fieldnames or []):
            raise ValueError(
                f"group column '{group_column}' not found in {path}; "
                f"available columns: {reader.fieldnames}"
            )
        for row in reader:
            raw = row.get(value_column, "")
            if raw is None or str(raw).strip() == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if not math.isfinite(value):
                continue
            label = row.get(group_column, "overall") if group_column else "overall"
            groups[label].append(value)
    if not groups:
        raise ValueError(f"no usable numeric data found in column '{value_column}'")
    return dict(groups)


def _format_ri_block(ri: ReferenceInterval, indent: str = "  ") -> str:
    ci_pct = int(round(ri.ci_level * 100))
    lines = [
        f"{indent}n = {ri.n_total} (used {ri.n_used}, "
        f"{ri.n_outliers} excluded as outliers)",
        f"{indent}Reference interval (2.5th-97.5th percentile): "
        f"{ri.lower_limit:.3f} - {ri.upper_limit:.3f}",
        f"{indent}{ci_pct}% CI on lower limit: "
        f"{ri.lower_ci[0]:.3f} - {ri.lower_ci[1]:.3f}",
        f"{indent}{ci_pct}% CI on upper limit: "
        f"{ri.upper_ci[0]:.3f} - {ri.upper_ci[1]:.3f}",
    ]
    if ri.outlier_values:
        lines.append(f"{indent}Excluded outlier values: {ri.outlier_values}")
    if ri.below_min_n:
        lines.append(
            f"{indent}WARNING: n={ri.n_used} is below the CLSI-recommended "
            f"minimum of n={CLSI_RECOMMENDED_MIN_N} for the nonparametric "
            f"method. Treat this interval as provisional."
        )
    return "\n".join(lines)


def _format_hb_block(hb: HarrisBoydResult, indent: str = "  ") -> str:
    verdict = "PARTITION recommended" if hb.partition_recommended else "no partition needed"
    return (
        f"{indent}{hb.group_a} (n={hb.n_a}) vs {hb.group_b} (n={hb.n_b}): "
        f"z = {hb.z_statistic:.3f}, critical z (n*={hb.n_star}) = "
        f"{hb.z_critical:.3f} -> {verdict}"
    )


def build_text_report(
    value_column: str, group_column: str | None, analysis: PartitionAnalysis
) -> str:
    out = StringIO()
    out.write("Reference Interval Report\n")
    out.write("=" * 26 + "\n")
    out.write(f"Value column: {value_column}\n")
    out.write("Method: CLSI EP28-A3c nonparametric (rank-based) percentile method\n")
    out.write("Outlier method: Tukey's method (1.5 x IQR fences)\n")
    out.write(f"Confidence level: {int(round(analysis.overall.ci_level * 100))}%\n\n")

    out.write("Overall\n")
    out.write(_format_ri_block(analysis.overall) + "\n\n")

    if group_column and len(analysis.subgroups) > 1:
        out.write(f"Harris-Boyd partition test (group column: {group_column})\n")
        for hb in analysis.harris_boyd_pairs:
            out.write(_format_hb_block(hb) + "\n")
        out.write("\n")

        for label, ri in analysis.subgroups.items():
            out.write(f"Subgroup: {label}\n")
            out.write(_format_ri_block(ri) + "\n\n")

    return out.getvalue()


def build_csv_report(analysis: PartitionAnalysis) -> str:
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "group",
            "n_total",
            "n_used",
            "n_outliers_excluded",
            "lower_limit",
            "upper_limit",
            "ci_level",
            "lower_ci_low",
            "lower_ci_high",
            "upper_ci_low",
            "upper_ci_high",
            "below_clsi_min_n",
        ]
    )

    def row(ri: ReferenceInterval):
        writer.writerow(
            [
                ri.label,
                ri.n_total,
                ri.n_used,
                ri.n_outliers,
                f"{ri.lower_limit:.4f}",
                f"{ri.upper_limit:.4f}",
                ri.ci_level,
                f"{ri.lower_ci[0]:.4f}",
                f"{ri.lower_ci[1]:.4f}",
                f"{ri.upper_ci[0]:.4f}",
                f"{ri.upper_ci[1]:.4f}",
                ri.below_min_n,
            ]
        )

    row(analysis.overall)
    for ri in analysis.subgroups.values():
        row(ri)
    return out.getvalue()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compute clinical reference intervals from healthy-subject lab "
            "data using the CLSI EP28-A3c nonparametric percentile method."
        )
    )
    parser.add_argument("--input", required=True, help="path to a CSV file of lab results")
    parser.add_argument(
        "--value-column", required=True, help="name of the CSV column holding the lab values"
    )
    parser.add_argument(
        "--group-column",
        default=None,
        help="optional CSV column (e.g. sex, age_group) to partition subgroups on",
    )
    parser.add_argument(
        "--ci",
        type=float,
        default=0.90,
        help="confidence level for the reference limit CIs (default: 0.90, per CLSI)",
    )
    parser.add_argument(
        "--format", choices=["text", "csv"], default="text", help="report output format"
    )
    parser.add_argument(
        "--output", default=None, help="write the report to this file instead of stdout"
    )

    args = parser.parse_args(argv)

    if not math.isfinite(args.ci) or not (0 < args.ci < 1):
        parser.error("--ci must be finite and between 0 and 1 (e.g. 0.90)")
    if args.ci < 0.5:
        parser.error("--ci must be >= 0.5 (confidence level below 50% is not meaningful)")

    try:
        safe_path = _safe_resolve_path(args.input)
        groups = read_csv_column(str(safe_path), args.value_column, args.group_column)
        analysis = partition_and_compute(groups, ci_level=args.ci)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "csv":
        report = build_csv_report(analysis)
    else:
        report = build_text_report(args.value_column, args.group_column, analysis)

    if args.output:
        if ".." in Path(args.output).parts:
            print("Error: output path contains '..' traversal components", file=sys.stderr)
            return 1
        out_path = Path(args.output)
        if out_path.is_symlink():
            print("Error: output path must not be a symlink", file=sys.stderr)
            return 1
        try:
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                f.write(report)
        except OSError as exc:
            print(f"Error writing report: {exc}", file=sys.stderr)
            return 1
    else:
        print(report, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
