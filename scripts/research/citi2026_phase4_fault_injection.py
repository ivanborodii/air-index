#!/usr/bin/env python3
"""CITI-2026 Phase 4 — whole-day train/test split + controlled fault injection.

The task brief's own top-level rule ("Split data by whole days BEFORE any
fault injection to prevent leakage") means the day-level split has to
happen here, even though it reads like a Phase 5 concern -- done once,
here, and carried forward unchanged into every later phase.

Fault channels: the four redundant-pair channels (scd_temp_c, bme_temp_c,
scd_humidity_pct, bme_humidity_pct) -- these are the ones with a real
second sensor to cross-check against, which is the whole mechanism this
paper is about. CO2/PM/pressure stay clean (they are Phase 3's independent
label source and must never be corrupted by this phase).

Four fault types, amplitude in multiples of each channel's OWN MAD (of its
first-difference series, i.e. typical sample-to-sample step size -- NOT the
whole-distribution MAD, which would conflate real diurnal swings with
short-term noise scale):

  - gradual_shift: linear ramp 0 -> k*MAD over 10 min, then holds at k*MAD
    for a further 20 min (30 min total).
  - spike: a single-sample impulse of +/-k*MAD (sign drawn per instance).
  - noise_burst: added zero-mean Gaussian noise, std=k*MAD, for 30 min.
  - stuck_value: freezes the reading at its value at fault onset. Has NO
    amplitude parameter (freezing is amplitude-agnostic by construction) --
    disclosed rather than force-fit into the amplitude grid; its grid
    dimension is DURATION instead (2.5/5/10/20/40 min), documented as a
    deliberate, different choice for this one fault type.

Amplitude grid: 0.5, 1, 2, 4, 8 x MAD (per the brief). 20 replicates per
(channel, fault_type, grid_value) combination, seeded (SEED=42) for exact
reproducibility. A fault instance's [start, end) window is constrained to
a single calendar day (so it belongs unambiguously to one split) and to
rows NOT already failing that channel's Phase-0 hard-range check (so the
"true" pre-injection signal at the injection site is itself not already
known-garbage). No two faults on the SAME channel are allowed to overlap;
faults on DIFFERENT channels may coincide in time (realistic, not
prohibited by the brief).

Output: a NEW dataset file (never touches the Phase 0/1/2 dataset) with
one row per original sample, one `<channel>_faulted` value column and one
`<channel>_fault_active` ground-truth boolean per injectable channel, plus
a `fault_injection_log` table with full provenance for every instance.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "citi2026"
RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase4"
DOCS_OUT = REPO_ROOT / "docs" / "citi2026_phase4_fault_injection.md"

SEED = 42
TRAIN_FRACTION = 0.70
INJECT_CHANNELS = ["scd_temp_c", "bme_temp_c", "scd_humidity_pct", "bme_humidity_pct"]
AMPLITUDE_GRID = [0.5, 1.0, 2.0, 4.0, 8.0]          # x channel MAD
STUCK_DURATION_GRID_SAMPLES = [5, 10, 20, 40, 80]    # 2.5/5/10/20/40 min
N_REPLICATES = 20
RAMP_MINUTES = 10
HOLD_MINUTES = 20
BURST_MINUTES = 30
EXCLUDED_DAYS = {pd.Timestamp("2026-09-13").date(), pd.Timestamp("2026-09-14").date()}


def find_latest_analysis_dataset() -> Path:
    candidates = sorted(glob.glob(str(DATA_DIR / "analysis_dataset_*.duckdb")))
    if not candidates:
        raise SystemExit("No Phase 0/2 analysis dataset found.")
    return Path(candidates[-1])


def make_day_split(days: list, rng: np.random.Generator) -> dict:
    """Whole-day split, stratified by month, fixed seed. Returns day -> split."""
    df = pd.DataFrame({"day": days})
    df["month"] = pd.to_datetime(df["day"]).dt.month
    split = {}
    for month, grp in df.groupby("month"):
        eligible = [d for d in grp["day"] if d not in EXCLUDED_DAYS]
        shuffled = list(eligible)
        rng.shuffle(shuffled)
        n_train = round(len(shuffled) * TRAIN_FRACTION)
        for d in shuffled[:n_train]:
            split[d] = "train"
        for d in shuffled[n_train:]:
            split[d] = "test"
    for d in EXCLUDED_DAYS:
        if d in df["day"].values:
            split[d] = "excluded"
    return split


def channel_mad_of_diff(series: pd.Series, hard_fail: pd.Series) -> float:
    clean = series.where(~hard_fail)
    diffs = clean.diff().dropna()
    med = diffs.median()
    return float((diffs - med).abs().median())


def day_bounds(day_idx: pd.Index) -> tuple[int, int]:
    return day_idx.min(), day_idx.max()


def main() -> None:
    rng = np.random.default_rng(SEED)

    ds_path = find_latest_analysis_dataset()
    con = duckdb.connect(str(ds_path), read_only=True)
    hard_cols = [f"hardcheck_fail_{c}" for c in INJECT_CHANNELS]
    cols = ["ts"] + INJECT_CHANNELS + hard_cols
    df = con.execute(f"SELECT {', '.join(cols)} FROM raw_observations_analysis ORDER BY ts").df()
    con.close()

    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["day"] = df["ts"].dt.tz_convert("Europe/Kyiv").dt.date
    df = df.reset_index(drop=True)

    events = pd.read_csv(
        REPO_ROOT / "research_results" / "citi2026" / "phase3" / "event_intervals.csv",
        parse_dates=["start_ts", "end_ts"],
    )

    # --- day split ---
    all_days = sorted(df["day"].unique())
    split_map = make_day_split(all_days, rng)
    df["day_split"] = df["day"].map(split_map)
    pd.DataFrame({"day": list(split_map.keys()), "split": list(split_map.values())}) \
        .sort_values("day").to_csv(RESULTS_DIR / "day_split.csv", index=False)

    # --- per-channel MAD-of-diff (computed over TRAIN days only, to avoid
    # any information from test days leaking into the amplitude scale used
    # to construct the benchmark) ---
    channel_mad = {}
    train_mask = df["day_split"] == "train"
    for ch in INJECT_CHANNELS:
        channel_mad[ch] = channel_mad_of_diff(
            df.loc[train_mask, ch], df.loc[train_mask, f"hardcheck_fail_{ch}"]
        )
    with open(RESULTS_DIR / "channel_mad.json", "w") as f:
        json.dump(channel_mad, f, indent=2)

    day_groups = {d: idx for d, idx in df.groupby("day").groups.items() if d not in EXCLUDED_DAYS}
    day_list = list(day_groups.keys())

    def event_overlap(start_ts, end_ts) -> bool:
        return bool(((events["start_ts"] < end_ts) & (events["end_ts"] > start_ts)).any())

    def find_valid_start(channel: str, duration: int, occupied: np.ndarray, rng: np.random.Generator, max_tries=200):
        hard_fail = df[f"hardcheck_fail_{channel}"].to_numpy()
        for _ in range(max_tries):
            day = day_list[rng.integers(len(day_list))]
            idx = day_groups[day]
            lo, hi = idx.min(), idx.max()
            if hi - lo + 1 < duration:
                continue
            start = rng.integers(lo, hi - duration + 2)
            end = start + duration  # exclusive
            if end - 1 > hi:
                continue
            if hard_fail[start:end].any():
                continue
            if occupied[start:end].any():
                continue
            return start, end, day
        return None

    faulted = {ch: df[ch].to_numpy(dtype=float).copy() for ch in INJECT_CHANNELS}
    active = {ch: np.zeros(len(df), dtype=bool) for ch in INJECT_CHANNELS}
    fault_id_arr = {ch: np.full(len(df), -1, dtype=int) for ch in INJECT_CHANNELS}
    occupied = {ch: np.zeros(len(df), dtype=bool) for ch in INJECT_CHANNELS}

    log_rows = []
    fault_id_counter = 0

    def inject(channel, fault_type, param_type, param_value, start, end, day, tag):
        nonlocal fault_id_counter
        mad = channel_mad[channel]
        true_vals = df[channel].to_numpy(dtype=float)[start:end]
        if np.isnan(true_vals).any():
            return False
        n = end - start
        if fault_type == "gradual_shift":
            ramp_n = min(int(RAMP_MINUTES * 60 / 30), n)
            hold_n = n - ramp_n
            ramp = np.linspace(0, param_value * mad, ramp_n, endpoint=False)
            hold = np.full(hold_n, param_value * mad)
            offset = np.concatenate([ramp, hold])
            new_vals = true_vals + offset
        elif fault_type == "spike":
            sign = rng.choice([-1.0, 1.0])
            new_vals = true_vals.copy()
            new_vals[0] = true_vals[0] + sign * param_value * mad
        elif fault_type == "noise_burst":
            noise = rng.normal(0, param_value * mad, size=n)
            new_vals = true_vals + noise
        elif fault_type == "stuck_value":
            new_vals = np.full(n, true_vals[0])
        else:
            raise ValueError(fault_type)

        faulted[channel][start:end] = new_vals
        active[channel][start:end] = True
        fault_id_arr[channel][start:end] = fault_id_counter
        occupied[channel][start:end] = True

        start_ts, end_ts = df["ts"].iloc[start], df["ts"].iloc[end - 1]
        log_rows.append({
            "fault_id": fault_id_counter, "channel": channel, "fault_type": fault_type,
            "param_type": param_type, "param_value": param_value,
            "channel_mad_used": mad, "start_idx": int(start), "end_idx": int(end) - 1,
            "n_samples": n, "start_ts": start_ts, "end_ts": end_ts, "day": day,
            "split": split_map[day], "overlaps_real_event": event_overlap(start_ts, end_ts),
        })
        fault_id_counter += 1
        return True

    for channel in INJECT_CHANNELS:
        for fault_type in ["gradual_shift", "spike", "noise_burst"]:
            duration = {
                "gradual_shift": int((RAMP_MINUTES + HOLD_MINUTES) * 60 / 30),
                "spike": 1,
                "noise_burst": int(BURST_MINUTES * 60 / 30),
            }[fault_type]
            for amp in AMPLITUDE_GRID:
                placed = 0
                for _ in range(N_REPLICATES):
                    result = find_valid_start(channel, duration, occupied[channel], rng)
                    if result is None:
                        continue
                    start, end, day = result
                    if inject(channel, fault_type, "amplitude_mad_multiple", amp, start, end, day, None):
                        placed += 1
        for dur in STUCK_DURATION_GRID_SAMPLES:
            for _ in range(N_REPLICATES):
                result = find_valid_start(channel, dur, occupied[channel], rng)
                if result is None:
                    continue
                start, end, day = result
                inject(channel, "stuck_value", "duration_samples", dur, start, end, day, None)

    log_df = pd.DataFrame(log_rows)
    log_df.to_csv(RESULTS_DIR / "fault_injection_log.csv", index=False)

    # --- write output dataset ---
    out_path = DATA_DIR / "injected_dataset.duckdb"
    out = duckdb.connect(str(out_path))
    out_df = df[["ts", "day", "day_split"] + INJECT_CHANNELS].copy()
    for ch in INJECT_CHANNELS:
        out_df[f"{ch}_faulted"] = faulted[ch]
        out_df[f"{ch}_fault_active"] = active[ch]
        out_df[f"{ch}_fault_id"] = fault_id_arr[ch]
    out.register("out_df", out_df)
    out.execute("CREATE OR REPLACE TABLE observations_injected AS SELECT * FROM out_df")
    out.register("log_df", log_df)
    out.execute("CREATE OR REPLACE TABLE fault_injection_log AS SELECT * FROM log_df")
    out.execute("CHECKPOINT")
    out.close()

    # --- summary doc ---
    lines = []
    lines.append("# CITI-2026 Phase 4 — Day Split & Controlled Fault Injection")
    lines.append("")
    lines.append(f"Seed: **{SEED}** (all randomness in this phase — day-split shuffling and fault "
                  f"placement — comes from one `np.random.default_rng({SEED})`).")
    lines.append("")
    lines.append("## Day split")
    lines.append("")
    split_counts = pd.Series(split_map).value_counts()
    for s, n in split_counts.items():
        lines.append(f"- {s}: {n} days")
    lines.append("")
    lines.append(
        f"Stratified by calendar month, {TRAIN_FRACTION:.0%}/{1-TRAIN_FRACTION:.0%} train/test within "
        "each month. 2026-09-13/09-14 (the venv-outage days, <20% coverage each) are excluded from "
        "both splits entirely — full table: `research_results/citi2026/phase4/day_split.csv`."
    )
    lines.append("")
    lines.append("## Channel MAD (of first-difference, TRAIN days only)")
    lines.append("")
    lines.append("| channel | MAD of diff (used as the amplitude-grid unit) |")
    lines.append("|---|---:|")
    for ch, mad in channel_mad.items():
        lines.append(f"| {ch} | {mad:.5f} |")
    lines.append("")
    lines.append(
        "Computed on TRAIN days only, so no information from held-out test days leaks into the "
        "amplitude scale used to build the injected benchmark."
    )
    lines.append("")
    lines.append("## Injected faults")
    lines.append("")
    lines.append(f"Total instances: **{len(log_df):,}** across {len(INJECT_CHANNELS)} channels x "
                  f"4 fault types.")
    lines.append("")
    lines.append("| fault type | channel | grid dimension | instances placed |")
    lines.append("|---|---|---|---:|")
    for (ft, ch), grp in log_df.groupby(["fault_type", "channel"]):
        dim = "amplitude (x MAD)" if ft != "stuck_value" else "duration (samples)"
        lines.append(f"| {ft} | {ch} | {dim} | {len(grp)} |")
    lines.append("")
    by_split = log_df["split"].value_counts()
    lines.append(f"By split: " + ", ".join(f"{s}={n}" for s, n in by_split.items()))
    lines.append("")
    overlap_pct = 100 * log_df["overlaps_real_event"].mean()
    lines.append(
        f"**{overlap_pct:.1f}%** of injected faults temporally overlap a Phase 3 weak-labelled "
        "real event — placement was uniformly random (not deliberately avoiding or seeking "
        "overlap), so this fraction reflects the real event base rate (~6.5% of samples) rather "
        "than a designed stress test; it is still enough overlapping instances "
        f"({int(log_df['overlaps_real_event'].sum())}) for Phase 7's false-event-rate metric to "
        "be computed meaningfully, not just theoretically defined."
    )
    lines.append("")
    lines.append(
        f"Any placement attempt that could not find a valid, non-overlapping, hard-range-clean "
        f"window within {200} tries was skipped rather than forced — see the per-combination "
        "counts above for any shortfall below the requested 20 replicates."
    )
    lines.append("")
    lines.append("## Fault shape parameters (fixed, only amplitude/duration varies per the grid)")
    lines.append("")
    lines.append(f"- gradual_shift: {RAMP_MINUTES} min linear ramp to target, then holds {HOLD_MINUTES} min "
                  f"({RAMP_MINUTES+HOLD_MINUTES} min total)")
    lines.append("- spike: single-sample impulse, random sign")
    lines.append(f"- noise_burst: {BURST_MINUTES} min of added zero-mean Gaussian noise, std = k x channel MAD")
    lines.append("- stuck_value: freezes at the onset value; NO amplitude parameter (disclosed, not "
                  "forced into the amplitude grid) — its grid dimension is duration instead "
                  f"({STUCK_DURATION_GRID_SAMPLES} samples = "
                  f"{[d*30/60 for d in STUCK_DURATION_GRID_SAMPLES]} min)")
    lines.append("")
    lines.append(
        "Output: `data/citi2026/injected_dataset.duckdb` (`observations_injected` + "
        "`fault_injection_log` tables). Full per-instance log: "
        "`research_results/citi2026/phase4/fault_injection_log.csv`."
    )

    DOCS_OUT.write_text("\n".join(lines))
    print(f"Injected {len(log_df):,} fault instances. Split: {dict(split_counts)}")
    print(f"Doc written: {DOCS_OUT}")


if __name__ == "__main__":
    main()
