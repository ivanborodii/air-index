"""Section 13 tests for the 2026-08 research protocol (data-interval
boundaries, calibration/validation split integrity, estimation-direction
arithmetic, class ordering, and artifact/reproducibility guarantees for the
generated research_results/runs/20260817_expanded_dataset_v1/ package).

Deliberately does NOT re-test production modules already covered elsewhere
(test_hampel_causal.py, test_fault_injection.py, test_multi_component_grid.py,
etc.) -- only the NEW logic this research task added.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from iaq_hfis.constants import CLASS_ORDER, CLASS_SEVERITY
from iaq_hfis.research_helpers import (
    classify_estimation_direction,
    is_within_requested_interval,
    scenario_family,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_DIR = REPO_ROOT / "research_results" / "runs" / "20260817_expanded_dataset_v1"


# --- estimation direction (underestimation/overestimation) arithmetic ---

def test_classify_estimation_direction_under_when_less_adverse():
    assert classify_estimation_direction("Favourable", "Critical", CLASS_SEVERITY) == "over"
    assert classify_estimation_direction("Critical", "Favourable", CLASS_SEVERITY) == "under"


def test_classify_estimation_direction_exact_when_same_severity():
    assert classify_estimation_direction("Degraded", "Degraded", CLASS_SEVERITY) == "exact"


def test_classify_estimation_direction_none_when_incomparable():
    assert classify_estimation_direction(None, "Critical", CLASS_SEVERITY) is None
    assert classify_estimation_direction("Critical", None, CLASS_SEVERITY) is None
    assert classify_estimation_direction("NotARealClass", "Critical", CLASS_SEVERITY) is None


def test_classify_estimation_direction_covers_every_class_pair():
    # Exhaustive: every (true, predicted) pair over CLASS_ORDER must resolve
    # to exactly one of under/over/exact, never None, never raise.
    for true_cls in CLASS_ORDER:
        for pred_cls in CLASS_ORDER:
            result = classify_estimation_direction(true_cls, pred_cls, CLASS_SEVERITY)
            assert result in ("under", "over", "exact")
            expected = "exact" if true_cls == pred_cls else (
                "over" if CLASS_SEVERITY[pred_cls] > CLASS_SEVERITY[true_cls] else "under"
            )
            assert result == expected


# --- UTC data-interval boundary (task section 3: start inclusive, end exclusive) ---

START = datetime(2026, 6, 18, 0, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 16, 0, 0, 0, tzinfo=timezone.utc)


def test_interval_includes_start_instant():
    assert is_within_requested_interval(START, START, END) is True


def test_interval_excludes_end_instant():
    # Task section 3 is explicit: "every measurement from 16 August 2026 or
    # later is excluded" -- the boundary instant itself must NOT be included.
    assert is_within_requested_interval(END, START, END) is False


def test_interval_includes_last_moment_of_aug_15():
    last_moment = datetime(2026, 8, 15, 23, 59, 59, 999999, tzinfo=timezone.utc)
    assert is_within_requested_interval(last_moment, START, END) is True


def test_interval_excludes_before_start():
    before = datetime(2026, 6, 17, 23, 59, 59, tzinfo=timezone.utc)
    assert is_within_requested_interval(before, START, END) is False


# --- calibration/validation split integrity (scenario_family grouping) ---

def test_scenario_family_grouping_prevents_split_overlap():
    # A deterministic group split (as task section 5.2 requires) groups by
    # scenario_family, not raw scenario_id -- verify the calibration/
    # validation variants of the SAME family always map to the same key, so
    # a group-based split can never place them in different groups.
    calib_id, valid_id = "co2_single_spike_calibration", "co2_single_spike_validation"
    assert scenario_family(calib_id) == scenario_family(valid_id)


def test_scenario_family_distinguishes_different_families():
    assert scenario_family("co2_single_spike_calibration") != scenario_family("co2_persistent_real_change_calibration")


# --- class ordering: read from config, never assumed ---

def test_class_order_is_favourable_to_critical():
    assert CLASS_ORDER == ["Favourable", "Acceptable", "Degraded", "Critical"]


def test_class_severity_matches_class_order_rank():
    for rank, cls in enumerate(CLASS_ORDER):
        assert CLASS_SEVERITY[cls] == rank


# --- Section-3 snapshot: no data leaked outside the requested interval ---

@pytest.mark.skipif(not (RUN_DIR / "snapshot" / "data_interval_verification.json").exists(), reason="section-3 snapshot not yet generated in this checkout")
def test_snapshot_has_zero_rows_outside_requested_interval():
    report = json.loads((RUN_DIR / "snapshot" / "data_interval_verification.json").read_text())
    assert report["rows_outside_requested_interval_found_in_selection"] == 0
    assert report["duplicate_ts_count"] == 0
    assert report["timestamp_ordering_violations"] == 0
    assert report["selected_min_ts"].startswith("2026-06-18")
    assert report["selected_max_ts"].startswith("2026-08-15")


# --- Missing-data-strategy artifacts: existence + plausible row counts ---

MISSING_DATA_DIR = RUN_DIR / "missing_data_strategy"


@pytest.mark.skipif(not MISSING_DATA_DIR.exists(), reason="section-6 missing-data-strategy run not yet generated in this checkout")
def test_missing_data_strategy_required_artifacts_exist():
    required = [
        "missing_data_strategy_predictions.csv",
        "missing_data_strategy_summary.csv",
        "missing_data_confusion_matrices.csv",
        "missing_data_bootstrap_intervals.csv",
        "missing_data_strategy_comparison.png",
        "missing_data_strategy_comparison.svg",
        "missing_data_strategy_metadata.json",
    ]
    for name in required:
        path = MISSING_DATA_DIR / name
        assert path.exists(), f"missing required artifact: {name}"
        assert path.stat().st_size > 0, f"required artifact is empty: {name}"


@pytest.mark.skipif(not MISSING_DATA_DIR.exists(), reason="section-6 missing-data-strategy run not yet generated in this checkout")
def test_missing_data_strategy_summary_covers_every_case_split_strategy_combination():
    import pandas as pd

    summary = pd.read_csv(MISSING_DATA_DIR / "missing_data_strategy_summary.csv")
    metadata = json.loads((MISSING_DATA_DIR / "missing_data_strategy_metadata.json").read_text())
    n_cases = len(metadata["masking_cases"])
    n_strategies = len(metadata["strategies"])
    # 2 dataset splits (calibration, validation) x every case x every strategy.
    assert len(summary) == n_cases * n_strategies * 2


@pytest.mark.skipif(not MISSING_DATA_DIR.exists(), reason="section-6 missing-data-strategy run not yet generated in this checkout")
def test_missing_data_strategy_metadata_records_seed_and_class_order():
    metadata = json.loads((MISSING_DATA_DIR / "missing_data_strategy_metadata.json").read_text())
    assert metadata["bootstrap_seed"] == 20260815
    assert metadata["class_order_low_to_high_severity"] == CLASS_ORDER


@pytest.mark.skipif(not MISSING_DATA_DIR.exists(), reason="section-6 missing-data-strategy run not yet generated in this checkout")
def test_missing_data_strategy_no_nonfinite_in_summary_metrics():
    import math

    import pandas as pd

    summary = pd.read_csv(MISSING_DATA_DIR / "missing_data_strategy_summary.csv")
    numeric_cols = ["mae", "rmse", "class_agreement_rate", "underestimation_rate", "overestimation_rate"]
    for col in numeric_cols:
        values = summary[col].dropna()
        assert all(math.isfinite(v) for v in values), f"non-finite value found in {col}"


# --- Static safety check: research scripts never open the production
# air-monitor DB for writing (task section 1: read-only access only). ---

RESEARCH_SCRIPTS_DIR = REPO_ROOT / "scripts" / "research"


def test_research_scripts_never_write_to_raw_observations():
    # Real write verbs against the production raw table -- not a blanket
    # string ban on "air_monitor.duckdb" (several scripts legitimately
    # mention it in read-only-access comments/notes).
    forbidden_snippets = ["DELETE FROM raw_observations", "UPDATE raw_observations", "INSERT INTO raw_observations", "DROP TABLE raw_observations"]
    offenders = []
    for path in RESEARCH_SCRIPTS_DIR.glob("*.py"):
        text = path.read_text()
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.name}: contains {snippet!r}")
    assert not offenders, "research script(s) reference forbidden raw-write patterns:\n" + "\n".join(offenders)


def test_research_scripts_open_air_monitor_source_only_via_readonly_helper():
    # Every script that touches the air-monitor DB does so through
    # iaq_hfis.db.AirMonitorSource (a read-only snapshot context manager) or
    # settings.paths.derived_db_path (this project's OWN derived-results DB,
    # never the production one) -- never a raw duckdb.connect(...) straight
    # at settings.paths.air_monitor_db_path.
    offenders = []
    for path in RESEARCH_SCRIPTS_DIR.glob("*.py"):
        text = path.read_text()
        if "air_monitor_db_path" in text and "AirMonitorSource" not in text:
            offenders.append(path.name)
    assert not offenders, f"script(s) reference air_monitor_db_path without going through AirMonitorSource: {offenders}"
