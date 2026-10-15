"""Stage 02: PM2.5/PM10 merging rule (task 3.4), hourly index (3.5),
class distribution."""

import json

import numpy as np
import pandas as pd

from common import SEASONS, WORK, results_dir, spearman, stage_timer, write_table
from iaq_index.config import load_config
from iaq_index.index import compute_index_frame, compute_scores


def merge_rule(grid: pd.DataFrame, cfg) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    rule = cfg.raw["pm_merge_rule"]
    both = grid.dropna(subset=["pm25", "pm10"])
    d = compute_scores(both.assign(co2=np.nan, t=np.nan, rh=np.nan), cfg)
    both = both.assign(d25=d["d_pm25"].to_numpy(), d10=d["d_pm10"].to_numpy())

    corr_rows = []
    for (home, season), g in both.groupby(["home", "season"]):
        if len(g) >= rule["min_common_hours"]:
            corr_rows.append({"home": home, "season": season, "n_hours": len(g), "spearman": spearman(g.pm25, g.pm10)})
    corr = pd.DataFrame(corr_rows)
    med = corr.groupby("season").spearman.median()

    dev = both[np.maximum(both.d25, both.d10) > 0]
    dev = dev.assign(pm10_dom=dev.d10 > dev.d25)
    share_rows = [{"scope": "overall", "home": "ALL", "season": "ALL", "n_hours_deviation": len(dev),
                   "share_d10_gt_d25": dev.pm10_dom.mean()}]
    for s, g in dev.groupby("season"):
        share_rows.append({"scope": "season", "home": "ALL", "season": s, "n_hours_deviation": len(g),
                           "share_d10_gt_d25": g.pm10_dom.mean()})
    for h, g in dev.groupby("home"):
        share_rows.append({"scope": "home", "home": h, "season": "ALL", "n_hours_deviation": len(g),
                           "share_d10_gt_d25": g.pm10_dom.mean()})
    shares = pd.DataFrame(share_rows)
    per_home = shares[shares.scope == "home"].share_d10_gt_d25

    cond1 = bool(all(med.get(s, -1) > rule["min_median_spearman"] for s in SEASONS))
    overall_share = float(dev.pm10_dom.mean())
    cond2 = overall_share <= rule["max_share_pm10_dominant"]
    decision = {
        "median_spearman_by_season": {s: float(med.get(s, np.nan)) for s in SEASONS},
        "n_homes_by_season": corr.groupby("season").size().to_dict(),
        "condition1_spearman_gt": rule["min_median_spearman"], "condition1_holds": cond1,
        "share_d10_gt_d25_overall": overall_share,
        "share_d10_gt_d25_by_season": shares[shares.scope == "season"].set_index("season").share_d10_gt_d25.to_dict(),
        "share_d10_gt_d25_per_home_quantiles": {q: float(per_home.quantile(q)) for q in (0, .25, .5, .75, 1)},
        "n_homes_share_gt_limit": int((per_home > rule["max_share_pm10_dominant"]).sum()),
        "condition2_share_le": rule["max_share_pm10_dominant"], "condition2_holds": bool(cond2),
        "pm10_separate": not (cond1 and cond2),
    }
    return decision, corr, shares


def class_distribution(frame: pd.DataFrame, comps: list[str], names) -> pd.DataFrame:
    rows = []
    ent = {"I": "class_I", **{f"Q_{c}": f"class_{c}" for c in comps}}
    scopes = [("overall", None)] + [("season", "season"), ("home", "home"), ("home_season", ["home", "season"])]
    for scope, by in scopes:
        groups = [("ALL", frame)] if by is None else frame.groupby(by)
        for key, g in groups:
            home, season = ("ALL", "ALL")
            if scope == "season":
                season = key
            elif scope == "home":
                home = key
            elif scope == "home_season":
                home, season = key
            for e, col in ent.items():
                vc = g[col].value_counts().reindex(range(5), fill_value=0)
                n = int(vc.sum())
                for k in range(5):
                    rows.append({"scope": scope, "home": home, "season": season, "entity": e, "class_rank": k,
                                 "class": names[k], "n_hours": int(vc[k]), "share": vc[k] / n if n else np.nan})
    return pd.DataFrame(rows)


def main():
    with stage_timer("s02_index") as log:
        grid = pd.read_parquet(WORK / "grid.parquet")
        base = load_config()
        decision, corr, shares = merge_rule(grid, base)
        out = results_dir()
        write_table(corr, out / "T_pm_merge_spearman.csv")
        write_table(shares, out / "T_pm_merge_share.csv")
        (WORK / "pm_merge_decision.json").write_text(json.dumps(decision, indent=2))
        (out / "pm_merge_decision.json").write_text(json.dumps(decision, indent=2))
        log.info("merge rule: %s", decision)

        cfg = base.with_overrides(pm10_separate=decision["pm10_separate"])
        idx = compute_index_frame(grid, cfg)
        frame = pd.concat([grid, idx], axis=1)
        frame.to_parquet(WORK / "hourly_index_all.parquet", index=False)  # incl. hours without I
        hourly = frame[frame.I.notna()].drop(columns=["observed"])
        hourly.to_parquet(out / "hourly_index.parquet", index=False)
        comps = list(cfg.components)
        write_table(class_distribution(hourly, comps, cfg.class_names), out / "T_class_distribution.csv")
        s = {"n_grid_hours": len(grid), "n_hours_with_I": len(hourly),
             "share_grid_hours_with_I": len(hourly) / len(grid),
             "share_records_with_I": len(hourly) / int(grid.observed.sum()), "components": comps}
        (WORK / "s02_summary.json").write_text(json.dumps(s, indent=2))
        log.info("%s", s)


if __name__ == "__main__":
    main()
