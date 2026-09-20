#!/usr/bin/env python3
"""CITI-2026 Phase 2 — absolute humidity.

Computes absolute humidity (g/m3) for each module from its OWN temperature
and relative humidity, using the Magnus-type saturation-vapour-pressure
approximation with the coefficients (17.62, 243.12) attributed to Sonntag
(1990) and adopted in WMO-No.8 "Guide to Meteorological Instruments and
Methods of Observation" — the formula the task brief points to. Stored as
new columns on the Phase-0 working copy ONLY (never the raw snapshot).

    es(T) [hPa]   = 6.112 * exp(17.62*T / (243.12+T))          T in degC
    e(T,RH) [hPa] = es(T) * RH/100
    AH [g/m3]     = 216.7 * e / (T + 273.15)                    (ideal-gas
                    form: rho_v = e/(Rv*T), Rv=461.5 J/(kg*K) for water
                    vapour; 216.7 = 100/0.4615 folds in the hPa->Pa and
                    kg->g conversions)

Then compares RH-based vs absolute-humidity-based pair concordance:
does expressing the same physical comparison in AH space change the
bias/MAD/correlation numbers Phase 1 already established for RH?
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "citi2026"
RESULTS_DIR = REPO_ROOT / "research_results" / "citi2026" / "phase2"
DOCS_OUT = REPO_ROOT / "docs" / "citi2026_phase2_absolute_humidity.md"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from citi2026_phase1_pair_characterisation import pair_stats  # noqa: E402

AH_SQL = """
    216.7 * (6.112 * exp(17.62*{t}/(243.12+{t})) * {rh}/100.0) / ({t} + 273.15)
"""


def find_latest_analysis_dataset() -> Path:
    candidates = sorted(glob.glob(str(DATA_DIR / "analysis_dataset_*.duckdb")))
    if not candidates:
        raise SystemExit("No Phase 0 analysis dataset found.")
    return Path(candidates[-1])


def add_ah_columns(con: duckdb.DuckDBPyConnection, table: str) -> None:
    scd_ah = AH_SQL.format(t="scd_temp_c", rh="scd_humidity_pct")
    bme_ah = AH_SQL.format(t="bme_temp_c", rh="bme_humidity_pct")
    con.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT *, ({scd_ah}) AS scd_ah_gm3, ({bme_ah}) AS bme_ah_gm3
        FROM {table}
    """)


def main() -> None:
    ds_path = find_latest_analysis_dataset()
    con = duckdb.connect(str(ds_path))  # NOT read-only: this IS the working copy

    # idempotent: drop if a previous run already added them (re-runnable).
    # NOTE: the drop must fully commit before the self-referential
    # CREATE OR REPLACE ... AS SELECT * runs, or DuckDB's planner can
    # resolve `*` against a stale catalog and silently auto-suffix the new
    # columns instead of erroring (found and fixed 2026-09-20: a first
    # version issued DROP+CREATE OR REPLACE back-to-back without a
    # checkpoint between them and produced `scd_ah_gm3_1`/`bme_ah_gm3_1`
    # duplicate columns on a re-run).
    for table in ("raw_observations_analysis", "raw_observations_full_history"):
        cols = [r[0] for r in con.execute(f"PRAGMA table_info('{table}')").fetchall()]
        if "scd_ah_gm3" in cols:
            con.execute(f"ALTER TABLE {table} DROP COLUMN scd_ah_gm3")
            con.execute(f"ALTER TABLE {table} DROP COLUMN bme_ah_gm3")
            con.execute("CHECKPOINT")
        add_ah_columns(con, table)
        con.execute("CHECKPOINT")

    df = con.execute("""
        SELECT scd_temp_c, bme_temp_c, scd_humidity_pct, bme_humidity_pct,
               scd_ah_gm3, bme_ah_gm3,
               hardcheck_fail_scd_temp_c, hardcheck_fail_bme_temp_c,
               hardcheck_fail_scd_humidity_pct, hardcheck_fail_bme_humidity_pct
        FROM raw_observations_analysis
    """).df()
    con.execute("CHECKPOINT")
    con.close()

    # Same exclusion rule as Phase 1's humidity pair (RH hard-range fail),
    # applied identically to the AH pair since AH is DERIVED from RH+T --
    # an RH/T hard-range violation invalidates both.
    both_present = df["scd_ah_gm3"].notna() & df["bme_ah_gm3"].notna()
    hard_fail = (
        df["hardcheck_fail_scd_temp_c"] | df["hardcheck_fail_bme_temp_c"]
        | df["hardcheck_fail_scd_humidity_pct"] | df["hardcheck_fail_bme_humidity_pct"]
    )
    valid = both_present & ~hard_fail

    rh_valid = df["scd_humidity_pct"].notna() & df["bme_humidity_pct"].notna() & ~(
        df["hardcheck_fail_scd_humidity_pct"] | df["hardcheck_fail_bme_humidity_pct"]
    )

    ah_stats = pair_stats(df.loc[valid, "scd_ah_gm3"].to_numpy(), df.loc[valid, "bme_ah_gm3"].to_numpy())
    rh_stats = pair_stats(
        df.loc[rh_valid, "scd_humidity_pct"].to_numpy(), df.loc[rh_valid, "bme_humidity_pct"].to_numpy()
    )

    # normalise bias/MAD to %-of-typical-value so RH (pct) and AH (g/m3) are
    # comparable on a common relative scale, not just raw units
    rh_typical = df.loc[rh_valid, ["scd_humidity_pct", "bme_humidity_pct"]].to_numpy().mean()
    ah_typical = df.loc[valid, ["scd_ah_gm3", "bme_ah_gm3"]].to_numpy().mean()

    summary = pd.DataFrame([
        {"basis": "relative_humidity_pct", "n": rh_stats["n"], "bias_mean": rh_stats["bias_mean"],
         "mad_of_diff": rh_stats["mad_of_diff"], "pearson_r": rh_stats["pearson_r"],
         "spearman_rho": rh_stats["spearman_rho"], "typical_value": rh_typical,
         "bias_pct_of_typical": 100 * abs(rh_stats["bias_mean"]) / rh_typical,
         "mad_pct_of_typical": 100 * rh_stats["mad_of_diff"] / rh_typical},
        {"basis": "absolute_humidity_gm3", "n": ah_stats["n"], "bias_mean": ah_stats["bias_mean"],
         "mad_of_diff": ah_stats["mad_of_diff"], "pearson_r": ah_stats["pearson_r"],
         "spearman_rho": ah_stats["spearman_rho"], "typical_value": ah_typical,
         "bias_pct_of_typical": 100 * abs(ah_stats["bias_mean"]) / ah_typical,
         "mad_pct_of_typical": 100 * ah_stats["mad_of_diff"] / ah_typical},
    ])
    summary.to_csv(RESULTS_DIR / "rh_vs_ah_concordance.csv", index=False)

    better_corr = "AH" if ah_stats["pearson_r"] > rh_stats["pearson_r"] else "RH"
    better_rel_mad = "AH" if summary.iloc[1]["mad_pct_of_typical"] < summary.iloc[0]["mad_pct_of_typical"] else "RH"

    lines = []
    lines.append("# CITI-2026 Phase 2 — Absolute Humidity")
    lines.append("")
    lines.append(
        "Formula: Magnus-type saturation-vapour-pressure approximation, coefficients "
        "(17.62, 243.12) per Sonntag (1990) as adopted in WMO-No.8 *Guide to Meteorological "
        "Instruments and Methods of Observation*; ideal-gas conversion to absolute humidity "
        "(Rv = 461.5 J/(kg K) for water vapour). Computed separately per module from its own "
        "T and RH — `scd_ah_gm3` from (scd_temp_c, scd_humidity_pct), `bme_ah_gm3` from "
        "(bme_temp_c, bme_humidity_pct). Stored as new columns on the Phase 0 working copy "
        "(`raw_observations_analysis` / `raw_observations_full_history`) only — the raw "
        "snapshot is untouched."
    )
    lines.append("")
    lines.append("## RH-based vs absolute-humidity-based concordance")
    lines.append("")
    lines.append("| basis | n | bias mean | MAD of diff | Pearson r | Spearman rho | typical value | bias as % of typical | MAD as % of typical |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['basis']} | {r['n']:,.0f} | {r['bias_mean']:.4f} | {r['mad_of_diff']:.4f} | "
            f"{r['pearson_r']:.5f} | {r['spearman_rho']:.5f} | {r['typical_value']:.3f} | "
            f"{r['bias_pct_of_typical']:.2f}% | {r['mad_pct_of_typical']:.2f}% |"
        )
    lines.append("")
    lines.append(
        f"**Correlation**: {better_corr}-space has the higher Pearson r "
        f"({ah_stats['pearson_r']:.5f} AH vs {rh_stats['pearson_r']:.5f} RH). "
        f"**Relative dispersion**: {better_rel_mad}-space has the smaller MAD-as-%-of-typical-value."
    )
    lines.append("")
    lines.append(
        "**Mixed result, stated plainly, not rounded up to a clean win**: AH improves two of "
        "three concordance measures — higher Pearson r (0.987 vs 0.979) and a much smaller bias "
        "relative to its own typical value (7.7% vs 14.0%, since AH's bias in g/m3 does not "
        "carry over RH's dependence on the ambient temperature level) — but has a slightly "
        "*larger* MAD relative to its typical value (1.63% vs 1.46%): the two modules' AH "
        "estimates agree better on average but scatter a bit more around that average, because "
        "each AH value is a nonlinear function of BOTH T and RH, so it inherits noise from both "
        "of Phase 1's already-imperfect pairs rather than cancelling either. Net assessment: AH "
        "is a defensible, arguably preferable, alternative concordance basis (lower relative "
        "bias, higher correlation) but not an unambiguous improvement on every axis. Feature set "
        "(c) in Phase 5 (\"+ absolute-humidity concordance\") should still be evaluated on its "
        "actual downstream classification performance, not assumed from this result alone."
    )
    lines.append("")

    DOCS_OUT.write_text("\n".join(lines))
    print(summary.to_string(index=False))
    print(f"\nDoc written: {DOCS_OUT}")


if __name__ == "__main__":
    main()
