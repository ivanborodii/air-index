"""Stage 10: verification of the article's statements (task section 10) ->
T_text_check.csv. Nothing is tuned here: values are only recomputed and
compared."""

import json

import numpy as np
import pandas as pd

from common import WORK, main_config, read_table, results_dir, stage_timer, write_table
from iaq_index.index import integral_index
from iaq_index.scores import class_from_score


def main():
    with stage_timer("s10_text_check") as log:
        cfg = main_config()
        out = results_dir()
        s01 = json.loads((WORK / "s01_summary.json").read_text())
        merge = json.loads((WORK / "pm_merge_decision.json").read_text())
        t2 = read_table(out / "T2_horizons.csv")

        def t2v(series, h, col):
            return float(t2[(t2.series == series) & (t2.h.astype(str) == str(h))][col].iloc[0])

        rows = []

        def add(stmt, article, obtained, match, note=""):
            rows.append({"statement": stmt, "value_in_article": article, "obtained_value": obtained,
                         "match": "yes" if match else "no", "note": note})

        add("number of records / homes", "322 591 / 27", f"{s01['n_records']} / {s01['n_homes']}",
            s01["n_records"] == 322591 and s01["n_homes"] == 27)
        for name, label in [("pm25_gt_25", "PM2.5 > 25"), ("co2_gt_1220", "CO2 > 1220")]:
            v = t2v(name, "episodes", "median_episode_h_pooled")
            vh = t2v(name, "episodes", "median_of_home_median_episode_h")
            add(f"median duration of episodes {label}", "3 h", f"{v:g} h (pooled episodes); {vh:g} h (median of per-home medians)",
                v == 3)
        sp_pm, sp_co2 = t2v("pm25", 6, "median_spearman"), t2v("co2", 6, "median_spearman")
        add("median Spearman x(t)-x(t+6), PM2.5 / CO2", "0.68 / 0.59", f"{sp_pm:.2f} / {sp_co2:.2f}",
            round(sp_pm, 2) == 0.68 and round(sp_co2, 2) == 0.59)
        for x, art, unit, fmt in [("pm25", (14.3, 15.6), "ug/m3", "{:.1f}"), ("co2", (174, 172), "ppm", "{:.0f}")]:
            pp, ps = t2v(x, 6, "pooled_mae_persistence"), t2v(x, 6, "pooled_mae_same_hour_prev_day")
            mp, ms = t2v(x, 6, "median_mae_persistence"), t2v(x, 6, "median_mae_same_hour_prev_day")
            ok = float(fmt.format(pp)) == art[0] and float(fmt.format(ps)) == art[1]
            add(f"h=6 MAE persistence vs same hour previous day, {x}", f"{art[0]} vs {art[1]} {unit}",
                f"pooled: {fmt.format(pp)} vs {fmt.format(ps)}; median over homes: {fmt.format(mp)} vs {fmt.format(ms)} {unit}",
                ok, "pooled over all hours of all homes; common hours where x(t), x(t+6) and x(t-18) are present")
        ms = merge["median_spearman_by_season"]
        add("median Spearman PM2.5-PM10 over homes, both seasons", "> 0.9 (about 0.998)",
            f"heating {ms['heating']:.4f}; warm {ms['warm']:.4f}", merge["condition1_holds"])
        add("share of hours with d_PM10 > d_PM2.5", "<= 5%", f"{100 * merge['share_d10_gt_d25_overall']:.4f}% "
            f"(max per home {100 * merge['share_d10_gt_d25_per_home_quantiles']['1']:.4f}%)", merge["condition2_holds"])
        r = integral_index(np.array([[60, 0, 0], [80, 0, 0]], dtype=float), cfg)["I"]
        add("scores (60,0,0) -> I = 45; (80,0,0) -> I = 80", "45; 80", f"{r[0]:g}; {r[1]:g}", r[0] == 45 and r[1] == 80)
        Q = np.random.default_rng(42).uniform(0, 100, size=(100_000, 3))
        rr = integral_index(Q, cfg)
        gap = class_from_score(rr["Q_max"]) - class_from_score(rr["I"])
        hourly = pd.read_parquet(out / "hourly_index.parquet", columns=["Q_max", "I"])
        gap_d = class_from_score(hourly.Q_max.to_numpy()) - class_from_score(hourly.I.to_numpy())
        add("class of I never more than one class better than the worst component", "property of (6)-(7)",
            f"max class gap: {gap.max():g} on 1e5 random triples; {gap_d.max():g} on {len(hourly)} data hours",
            gap.max() <= 1 and gap_d.max() <= 1)
        claims = [
            ("novelty 1: validation on homes not used in training (S2)", "T6_regression.csv, T7_classification.csv (scheme = S2), groups.json"),
            ("novelty 2: direct forecast of I vs I from forecasts of indicators", "T8_direct_vs_indicators.csv, T_wilcoxon.csv"),
            ("novelty 3: component contribution per home and season", "T5_contribution.csv"),
        ]
        for c, f in claims:
            exists = all((out / x.strip().split(" ")[0]).exists() for x in f.split(","))
            add(c, "claim", f"supported by {f}", exists)
        t = pd.DataFrame(rows)
        write_table(t, out / "T_text_check.csv")
        log.info("\n%s", t.to_string())


if __name__ == "__main__":
    main()
