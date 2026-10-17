"""Stage 01: load, invalid-value rules, hourly grid, T1_dataset.csv."""

import json

import pandas as pd

from common import DATA_CSV, WORK, main_config, results_dir, stage_timer, write_table
from iaq_index.config import INDICATORS
from iaq_index.data import prepare


def main():
    with stage_timer("s01_data") as log:
        if not DATA_CSV.exists():
            raise SystemExit(f"dataset not found: {DATA_CSV} (see README: how to obtain it)")
        pp = main_config().raw["preprocessing"]
        raw, removed, grid = prepare(DATA_CSV, pp)
        out = results_dir()
        write_table(removed, out / "T_invalid_removed.csv")

        rows = []
        for home, g in grid.groupby("home"):
            r = raw[raw.home == home]
            row = {"home": home, "start": g.time.min(), "end": g.time.max(), "n_records": len(r),
                   "n_observed_days": r.time.dt.normalize().nunique(), "n_grid_hours": len(g),
                   "share_hours_no_record": 1 - g.observed.mean()}
            for x in INDICATORS:
                row[f"share_missing_{x}"] = g[x].isna().mean()
            row["share_all_five_present"] = g[INDICATORS].notna().all(axis=1).mean()
            rows.append(row)
        t1 = pd.DataFrame(rows)
        tot = {"home": "ALL", "start": grid.time.min(), "end": grid.time.max(), "n_records": len(raw),
               "n_observed_days": int(t1.n_observed_days.sum()), "n_grid_hours": len(grid),
               "share_hours_no_record": 1 - grid.observed.mean(),
               **{f"share_missing_{x}": grid[x].isna().mean() for x in INDICATORS},
               "share_all_five_present": grid[INDICATORS].notna().all(axis=1).mean()}
        t1 = pd.concat([t1, pd.DataFrame([tot])], ignore_index=True)
        write_table(t1, out / "T1_dataset.csv")

        summary = {"n_records": len(raw), "n_homes": int(raw.home.nunique()), "n_grid_hours": len(grid),
                   "share_missing_hours": float(1 - grid.observed.mean()),
                   "share_hours_all_five": float(tot["share_all_five_present"]),
                   "invalid_removed": removed.set_index("rule").n_values_removed.to_dict()}
        (WORK / "s01_summary.json").write_text(json.dumps(summary, indent=2))
        grid.to_parquet(WORK / "grid.parquet", index=False)
        log.info("%s", summary)


if __name__ == "__main__":
    main()
