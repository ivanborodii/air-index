"""Section 10: data-quality reason breakdown, by channel/day/hour, over the
expanded dataset. Purely descriptive counts from the real, persisted
observation_quality and iaq_index_results tables for one pipeline run -- no
hardware-cause speculation, per task instruction.

Outputs:
  reason_code_by_channel.csv        -- reason_code counts/rates per channel
  reason_code_by_channel_day.csv    -- per (channel, calendar day)
  reason_code_by_channel_hour.csv   -- per (channel, hour-of-day 0-23)
  completeness_status_by_day.csv    -- OK/PARTIAL/FAILED counts per day
  stage2_state_by_channel.csv       -- VALID/SUSPECT/INVALID/MISSING counts per channel
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path("/home/ivan/python_scripts/air_ml")
sys.path.insert(0, str(REPO_ROOT / "src"))
from iaq_hfis.config import load_settings  # noqa: E402

RUN_ID = "20260818_peer_review_revision_v2"
OUT_DIR = REPO_ROOT / "research_results" / "runs" / RUN_ID / "data_quality_reasons"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WINDOW_MINUTES = 15

if len(sys.argv) < 2:
    raise SystemExit("usage: data_quality_reason_analysis.py <pipeline_run_id>")
PIPELINE_RUN_ID = sys.argv[1]

settings = load_settings(REPO_ROOT / "config" / "iaq_hfis.yaml")
con = duckdb.connect(str(settings.paths.derived_db_path), read_only=True)

oq = con.execute(
    "SELECT ts, channel, stage1_state, stage2_state, usable, reason_codes FROM observation_quality WHERE pipeline_run_id = ?",
    [PIPELINE_RUN_ID],
).fetch_df()
idx = con.execute(
    "SELECT computed_ts, completeness_status FROM iaq_index_results WHERE pipeline_run_id = ? AND window_minutes = ?",
    [PIPELINE_RUN_ID, WINDOW_MINUTES],
).fetch_df()
con.close()

if oq.empty:
    raise SystemExit(f"No observation_quality rows for pipeline_run_id={PIPELINE_RUN_ID}")

oq["ts"] = pd.to_datetime(oq["ts"], utc=True)
oq["day"] = oq["ts"].dt.date
oq["hour"] = oq["ts"].dt.hour

exploded = oq.explode("reason_codes")
exploded_named = exploded[exploded["reason_codes"].notna()]

by_channel = exploded_named.groupby(["channel", "reason_codes"]).size().reset_index(name="n")
by_channel["rate_of_channel_rows"] = by_channel.apply(lambda r: r["n"] / len(oq[oq["channel"] == r["channel"]]), axis=1)
by_channel.to_csv(OUT_DIR / "reason_code_by_channel.csv", index=False)
# Task section 10 filename:
by_channel.rename(columns={"channel": "sensor_channel"}).to_csv(OUT_DIR / "data_quality_reason_by_sensor.csv", index=False)

by_channel_day = exploded_named.groupby(["channel", "day", "reason_codes"]).size().reset_index(name="n")
by_channel_day.to_csv(OUT_DIR / "reason_code_by_channel_day.csv", index=False)
reason_by_day = exploded_named.groupby(["day", "reason_codes"]).size().reset_index(name="n")
reason_by_day.to_csv(OUT_DIR / "data_quality_reason_by_day.csv", index=False)

by_channel_hour = exploded_named.groupby(["channel", "hour", "reason_codes"]).size().reset_index(name="n")
by_channel_hour.to_csv(OUT_DIR / "reason_code_by_channel_hour.csv", index=False)
reason_by_hour = exploded_named.groupby(["hour", "reason_codes"]).size().reset_index(name="n")
reason_by_hour.to_csv(OUT_DIR / "data_quality_reason_by_hour.csv", index=False)

stage2_by_channel = oq.groupby(["channel", "stage2_state"]).size().reset_index(name="n")
stage2_by_channel["rate"] = stage2_by_channel.apply(lambda r: r["n"] / len(oq[oq["channel"] == r["channel"]]), axis=1)
stage2_by_channel.to_csv(OUT_DIR / "stage2_state_by_channel.csv", index=False)

if not idx.empty:
    idx["computed_ts"] = pd.to_datetime(idx["computed_ts"], utc=True)
    idx["day"] = idx["computed_ts"].dt.date
    idx["hour"] = idx["computed_ts"].dt.hour
    completeness_by_day = idx.groupby(["day", "completeness_status"]).size().reset_index(name="n")
    completeness_by_day.to_csv(OUT_DIR / "completeness_status_by_day.csv", index=False)
    completeness_by_hour = idx.groupby(["hour", "completeness_status"]).size().reset_index(name="n")
    completeness_by_hour.to_csv(OUT_DIR / "completeness_status_by_hour.csv", index=False)

    # --- overall summary: status counts/shares + top reason-code counts +
    # which channel each reason is associated with (from the by-channel
    # table above, never invented) ---
    n_total_idx = len(idx)
    status_counts = idx["completeness_status"].value_counts()
    reason_totals = exploded_named.groupby("reason_codes").size().rename("n").reset_index()
    reason_totals["primary_associated_channel"] = reason_totals["reason_codes"].apply(
        lambda rc: by_channel[by_channel["reason_codes"] == rc].sort_values("n", ascending=False)["channel"].iloc[0]
        if (by_channel["reason_codes"] == rc).any() else None
    )
    summary_rows = [
        {"metric": f"completeness_status_count__{s}", "value": int(c)} for s, c in status_counts.items()
    ] + [
        {"metric": f"completeness_status_share__{s}", "value": float(c / n_total_idx)} for s, c in status_counts.items()
    ] + [
        {"metric": f"reason_code_total_count__{r.reason_codes}", "value": int(r.n)} for r in reason_totals.itertuples()
    ]
    pd.DataFrame(summary_rows).to_csv(OUT_DIR / "data_quality_reason_summary.csv", index=False)
    reason_totals.to_csv(OUT_DIR / "data_quality_reason_channel_association.csv", index=False)

    # --- combinations of reasons co-occurring on the same (ts, channel) row ---
    def _combo(codes):
        if not isinstance(codes, (list, np.ndarray)) or len(codes) == 0:
            return None
        return "+".join(sorted(set(codes)))

    oq["reason_combo"] = oq["reason_codes"].apply(_combo)
    combo_counts = oq[oq["reason_combo"].notna()]["reason_combo"].value_counts().rename_axis("reason_combination").reset_index(name="n")
    combo_counts.to_csv(OUT_DIR / "data_quality_reason_combinations.csv", index=False)

    # --- continuous PARTIAL/FAILED interval durations (repeated failure
    # periods), at the completeness_status level over computed_ts (assumes
    # a regular recompute grid; run_length is measured in consecutive
    # computed_ts steps, duration in wall-clock time between first/last). ---
    idx_sorted = idx.sort_values("computed_ts").reset_index(drop=True)
    idx_sorted["is_bad"] = idx_sorted["completeness_status"].isin(["PARTIAL", "FAILED"])
    idx_sorted["run_id"] = (idx_sorted["is_bad"] != idx_sorted["is_bad"].shift()).cumsum()
    bad_runs = idx_sorted[idx_sorted["is_bad"]].groupby("run_id").agg(
        start_ts=("computed_ts", "min"), end_ts=("computed_ts", "max"), n_steps=("computed_ts", "size"),
    ).reset_index(drop=True)
    bad_runs["duration_seconds"] = (bad_runs["end_ts"] - bad_runs["start_ts"]).dt.total_seconds()
    statuses_in_run = idx_sorted[idx_sorted["is_bad"]].groupby(
        (idx_sorted["is_bad"] != idx_sorted["is_bad"].shift()).cumsum()
    )["completeness_status"].agg(lambda s: "+".join(sorted(set(s))))
    bad_runs["statuses_present"] = statuses_in_run.reset_index(drop=True)
    bad_runs.to_csv(OUT_DIR / "data_quality_failure_intervals.csv", index=False)
else:
    completeness_by_day = pd.DataFrame()
    bad_runs = pd.DataFrame()

print(f"Wrote artifacts to {OUT_DIR}")
print(by_channel.to_string())
print(stage2_by_channel.to_string())
if not completeness_by_day.empty:
    print(completeness_by_day.groupby("completeness_status")["n"].sum().to_string())
if not bad_runs.empty:
    print(f"n_failure_intervals={len(bad_runs)}, longest={bad_runs['duration_seconds'].max()}s")
