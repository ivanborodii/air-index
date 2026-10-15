"""Stage 04: aggregation rules (mean, worst component, I, fuzzy method [18])
and sensitivity analysis -- task section 5."""

import json
from datetime import datetime

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from common import N_JOBS, REPO, WORK, main_config, results_dir, spearman, stage_timer, write_table
from iaq_index.config import INDICATORS
from iaq_index.index import compute_index_frame, dominance_flags
from iaq_index.scores import class_from_score

NAMES = ["EXCELLENT", "GOOD", "MODERATE", "LOW", "CRITICAL"]


# ---------------------------------------------------------------- fuzzy [18]
def _fuzzy_chunk(rows: list[tuple], room_override: str | None):
    """Runs the unchanged iaq_hfis Mamdani engine (config/ as is) for a chunk
    of hours. Returns (score, native 4-class label, profile key) per row;
    NaN/None where the [18] configuration defines no temperature profile."""
    from iaq_hfis import profiles
    from iaq_hfis.config import TemperatureProfileNotDefinedError, load_room_profiles, load_sensor_specs, load_settings
    from iaq_hfis.pipeline import build_runtime_context, infer_from_values

    s = load_settings(REPO / "config/iaq_hfis.yaml")
    rp = load_room_profiles(REPO / "config/room_profiles.yaml")
    ctx = build_runtime_context(s, load_sensor_specs(REPO / "config/sensor_specs.yaml"), rp,
                                set(s.schema_mapping.required_raw_columns))
    out = []
    for ts, pm25, pm10, co2, t, rh in rows:
        try:
            prof = profiles.select_room_season(rp, ts, s.profile_selection, room_override=room_override)
        except TemperatureProfileNotDefinedError:
            out.append((np.nan, None, None))
            continue
        vals = {"pm2_5": pm25, "pm10": pm10, "co2": co2, "temperature": t, "humidity": rh}
        _, idx = infer_from_values(ctx, vals, {"A", "V", "M"}, prof)
        out.append((idx.index_value, idx.index_class, f"{prof.room}/{prof.season}"))
    return out


def fuzzy_scores(hourly: pd.DataFrame, room_override=None) -> pd.DataFrame:
    rows = list(zip([t.to_pydatetime() for t in hourly.time], *(hourly[c].astype(float) for c in INDICATORS)))
    chunks = [rows[i:i + 20000] for i in range(0, len(rows), 20000)]
    res = Parallel(n_jobs=N_JOBS)(delayed(_fuzzy_chunk)(c, room_override) for c in chunks)
    flat = [r for part in res for r in part]
    return pd.DataFrame(flat, columns=["score_18", "class4_18", "profile_18"], index=hourly.index)


# ---------------------------------------------------------------- comparison
def compare_rules(df: pd.DataFrame, rules: dict[str, str]) -> pd.DataFrame:
    worst = class_from_score(df["Q_max"].to_numpy())
    cls_I = class_from_score(df["I"].to_numpy())
    rows = []
    for season, g_idx in [("ALL", df.index)] + [(s, g.index) for s, g in df.groupby("season")]:
        sel = df.index.isin(g_idx)
        for rule, col in rules.items():
            v = df.loc[sel, col].to_numpy()
            ok = ~np.isnan(v)
            c = class_from_score(v[ok])
            w = worst[sel][ok]
            ci = cls_I[sel][ok]
            row = {"rule": rule, "season": season, "n_hours": int(ok.sum())}
            for k in range(5):
                row[f"share_{NAMES[k]}"] = np.mean(c == k) if ok.any() else np.nan
            row["share_more_than_one_class_better_than_worst"] = np.mean(w - c > 1) if ok.any() else np.nan
            bad = w >= 3
            row["n_hours_worst_LOW_or_CRITICAL"] = int(bad.sum())
            row["share_hides_LOW_CRITICAL"] = np.mean(c[bad] <= 2) if bad.any() else np.nan
            row["class_agreement_with_I"] = np.mean(c == ci) if ok.any() else np.nan
            row["spearman_with_I"] = spearman(v[ok], df.loc[sel, "I"].to_numpy()[ok]) if ok.sum() > 2 else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- sensitivity
def trailing_pm(allh: pd.DataFrame, window_h: int, min_h: int) -> pd.DataFrame:
    out = allh.copy()
    for _, g in allh.groupby("home"):
        rows = g.index
        g = g.set_index("time")
        for x in ("pm25", "pm10"):
            r = g[x].rolling(f"{window_h}h", closed="right", min_periods=1)
            out.loc[rows, x] = r.mean().where(r.count() >= min_h).to_numpy()
    return out


def sensitivity(allh: pd.DataFrame, cfg) -> pd.DataFrame:
    sens = cfg.raw["sensitivity"]
    grid = allh[["home", "time", "season", *INDICATORS]]
    variants = {
        "base": (cfg, grid),
        "t_low_limit_17C": (cfg.with_overrides(t_low=sens["t_low_alt"]), grid),
        "co2_outdoor_400ppm": (cfg.with_overrides(co2_outdoor_ppm=sens["co2_outdoor_alt_ppm"]), grid),
        "pm_trailing_24h_mean": (cfg, trailing_pm(grid, sens["pm_trailing_window_hours"], sens["pm_trailing_min_hours"])),
    }
    comps = list(cfg.components)
    rows = []
    for name, (vcfg, g) in variants.items():
        f = pd.concat([g, compute_index_frame(g, vcfg)], axis=1)
        f = f[f.I.notna()]
        fl = pd.concat([f[["home", "season"]], dominance_flags(f, vcfg)], axis=1).dropna(subset=comps)
        for season, sub, flsub in [("ALL", f, fl)] + [(s, f[f.season == s], fl[fl.season == s]) for s in ("heating", "warm")]:
            row = {"variant": name, "season": season, "n_hours_I": len(sub)}
            vc = sub.class_I.value_counts(normalize=True).reindex(range(5), fill_value=0)
            for k in range(5):
                row[f"share_{NAMES[k]}"] = vc[k]
            per_home = flsub.groupby("home")[comps].mean()
            for c in comps:
                row[f"median_S_{c}_over_homes"] = per_home[c].median()
                row[f"pooled_S_{c}"] = flsub[c].mean()
            row["n_hours_I_gt_25"] = len(flsub)
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    with stage_timer("s04_aggregation") as log:
        cfg = main_config()
        out = results_dir()
        allh = pd.read_parquet(WORK / "hourly_index_all.parquet")
        hourly = allh[allh.I.notna()].copy()

        fz = WORK / "fuzzy18.parquet"
        if not fz.exists():
            f = fuzzy_scores(hourly)
            f2 = fuzzy_scores(hourly, room_override="general_residential")
            f["score_18_general_residential"] = f2["score_18"]
            f["profile_18_general_residential"] = f2["profile_18"]
            pd.concat([hourly[["home", "time"]], f], axis=1).to_parquet(fz, index=False)
        f = pd.read_parquet(fz)
        hourly["score_18"] = f["score_18"].to_numpy()
        hourly["score_18_gr"] = f["score_18_general_residential"].to_numpy()
        hourly["profile_18"] = f["profile_18"].to_numpy()

        rules = {"mean_Qbar": "Q_mean", "worst_Qmax": "Q_max", "model_I": "I",
                 "fuzzy18_kitchen_config_as_is": "score_18",
                 "fuzzy18_general_residential_warm_only": "score_18_gr"}
        t4 = compare_rules(hourly, rules)
        write_table(t4, out / "T4_aggregation_compare.csv")

        # [18] in its own 4 classes vs I merged to 4 classes (supplementary)
        ok = hourly.score_18.notna()
        i4 = np.clip(class_from_score(hourly.I.to_numpy()) - 1, 0, 3)  # EXCELLENT+GOOD -> one class
        sev = {"Favourable": 0, "Acceptable": 1, "Degraded": 2, "Critical": 3}
        f4 = f["class4_18"].map(sev).to_numpy()
        conf = pd.crosstab(pd.Series(class_from_score(hourly.I.to_numpy()), name="class_I"),
                           pd.Series(class_from_score(hourly.score_18.to_numpy()), name="class_18_5"))
        conf.index = [NAMES[int(i)] for i in conf.index]
        conf.columns = [NAMES[int(i)] for i in conf.columns]
        write_table(conf.reset_index(names="class_I"), out / "T4b_confusion_I_vs_fuzzy18.csv")
        extra = {
            "fuzzy18_profiles_used": hourly.profile_18.value_counts(dropna=False).to_dict(),
            "fuzzy18_general_residential_n_defined": int(hourly.score_18_gr.notna().sum()),
            "agreement_5class_thresholds_0_25_50_75": float(np.mean(class_from_score(hourly.score_18[ok]) == class_from_score(hourly.I[ok]))),
            "agreement_4class_native_vs_I_merged_excellent_good": float(np.mean(f4[ok.to_numpy()] == i4[ok.to_numpy()])),
            "spearman_score18_vs_I": spearman(hourly.score_18[ok], hourly.I[ok]),
            "fuzzy18_min_score": float(hourly.score_18.min()),
            "note": "[18] uses config/ as is: room=kitchen, its own season months (cold Oct-Mar, warm Apr-Sep), "
                    "fuzzy class boundaries 25/50/75 left-closed; EXCELLENT (score exactly 0) is unreachable for a centroid score.",
        }
        (out / "fuzzy18_comparison.json").write_text(json.dumps(extra, indent=2, ensure_ascii=False, default=str))
        log.info("%s", extra)

        t5b = sensitivity(allh, cfg)
        write_table(t5b, out / "T5b_sensitivity.csv")
        log.info("\n%s", t5b.to_string())


if __name__ == "__main__":
    main()
