"""Stage 05: justification of forecast horizons (T2) -- task section 6."""

import json

import numpy as np
import pandas as pd

from common import HORIZONS_ANALYSIS, WORK, episodes, pearson, results_dir, spearman, stage_timer, write_table
from iaq_index.config import INDICATORS

SERIES = INDICATORS + ["I"]
EPISODE_RULES = {"pm25_gt_25": ("pm25", 25), "co2_gt_1220": ("co2", 1220), "I_gt_25": ("I", 25),
                 "I_gt_50": ("I", 50), "I_gt_75": ("I", 75)}


def main():
    with stage_timer("s05_horizons") as log:
        allh = pd.read_parquet(WORK / "hourly_index_all.parquet")
        rows, pooled = [], []
        for x in SERIES:
            for h in HORIZONS_ANALYSIS:
                per_home = []
                pool_err = {"pers": [], "seas": [], "pers_all": []}
                for home, g in allh.groupby("home"):
                    s = g.set_index("time")[x]
                    fut = s.reindex(s.index + pd.Timedelta(hours=h)).to_numpy()
                    lag = s.reindex(s.index + pd.Timedelta(hours=h - 24)).to_numpy()
                    cur = s.to_numpy()
                    ok = ~np.isnan(cur) & ~np.isnan(fut)
                    ok3 = ok & ~np.isnan(lag)  # common set for the two naive forecasts
                    if ok.sum() < 200:
                        continue
                    per_home.append({
                        "home": home, "n_pairs": int(ok.sum()), "n_common_naive": int(ok3.sum()),
                        "spearman": spearman(cur[ok], fut[ok]), "pearson": pearson(cur[ok], fut[ok]),
                        "mae_persistence": np.mean(np.abs(fut[ok3] - cur[ok3])),
                        "mae_same_hour_prev_day": np.mean(np.abs(fut[ok3] - lag[ok3])),
                        "mae_persistence_all_pairs": np.mean(np.abs(fut[ok] - cur[ok])),
                    })
                    pool_err["pers"].append(np.abs(fut[ok3] - cur[ok3]))
                    pool_err["seas"].append(np.abs(fut[ok3] - lag[ok3]))
                ph = pd.DataFrame(per_home)
                rows.append({"series": x, "h": h, "n_homes": len(ph),
                             "median_spearman": ph.spearman.median(), "median_pearson": ph.pearson.median(),
                             "median_mae_persistence": ph.mae_persistence.median(),
                             "median_mae_same_hour_prev_day": ph.mae_same_hour_prev_day.median(),
                             "pooled_mae_persistence": np.concatenate(pool_err["pers"]).mean(),
                             "pooled_mae_same_hour_prev_day": np.concatenate(pool_err["seas"]).mean(),
                             "q1_spearman": ph.spearman.quantile(.25), "q3_spearman": ph.spearman.quantile(.75)})
                pooled.append(ph.assign(series=x, h=h))
        t2 = pd.DataFrame(rows)

        ep_rows = []
        for name, (x, thr) in EPISODE_RULES.items():
            lens, home_meds = [], []
            for _, g in allh.groupby("home"):
                e = episodes(g[x] > thr)
                lens.append(e)
                if len(e):
                    home_meds.append(np.median(e))
            allen = np.concatenate(lens)
            ep_rows.append({"series": name, "h": "episodes", "n_episodes": len(allen),
                            "median_episode_h_pooled": float(np.median(allen)) if len(allen) else np.nan,
                            "median_of_home_median_episode_h": float(np.median(home_meds)) if home_meds else np.nan,
                            "mean_episode_h_pooled": float(np.mean(allen)) if len(allen) else np.nan,
                            "q3_episode_h_pooled": float(np.quantile(allen, .75)) if len(allen) else np.nan,
                            "n_homes_with_episodes": len(home_meds)})
        t2 = pd.concat([t2, pd.DataFrame(ep_rows)], ignore_index=True)
        out = results_dir()
        write_table(t2, out / "T2_horizons.csv")
        write_table(pd.concat(pooled, ignore_index=True), out / "T2b_horizons_per_home.csv")
        log.info("\n%s", t2.to_string())


if __name__ == "__main__":
    main()
