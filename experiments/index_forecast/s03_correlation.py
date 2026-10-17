"""Stage 03: correlation of indicators (T3), I vs components, dominance
shares S_c (T5) -- task section 4."""

import itertools

import numpy as np
import pandas as pd

from common import WORK, main_config, pearson, results_dir, spearman, stage_timer, write_table
from iaq_index.config import INDICATORS
from iaq_index.index import dominance_flags

MIN_COMMON = 200


def _agg(v: pd.Series, prefix: str) -> dict:
    return {f"{prefix}_median": v.median(), f"{prefix}_q1": v.quantile(.25), f"{prefix}_q3": v.quantile(.75),
            f"{prefix}_min": v.min(), f"{prefix}_max": v.max()}


def indicator_correlations(allh: pd.DataFrame):
    per_home = []
    for (home, season), g in allh.groupby(["home", "season"]):
        for a, b in itertools.combinations(INDICATORS, 2):
            p = g[[a, b]].dropna()
            if len(p) < MIN_COMMON:
                continue
            per_home.append({"home": home, "season": season, "x": a, "y": b, "n": len(p),
                             "spearman": spearman(p[a], p[b]), "pearson": pearson(p[a], p[b])})
    per_home = pd.DataFrame(per_home)
    rows = []
    for season_key, sub in [("ALL", allh)] + list(allh.groupby("season")):
        for a, b in itertools.combinations(INDICATORS, 2):
            ph = per_home[(per_home.x == a) & (per_home.y == b)]
            if season_key != "ALL":
                ph = ph[ph.season == season_key]
            p = sub[[a, b]].dropna()
            row = {"season": season_key, "x": a, "y": b, "n_home_seasons": len(ph),
                   "n_homes": ph.home.nunique(), **_agg(ph.spearman, "spearman"), **_agg(ph.pearson, "pearson"),
                   "pooled_n": len(p), "pooled_spearman": spearman(p[a], p[b]), "pooled_pearson": pearson(p[a], p[b])}
            for m in ("spearman", "pearson"):
                med, pool = row[f"{m}_median"], row[f"pooled_{m}"]
                row[f"flag_{m}_pooled_vs_median"] = bool(abs(pool - med) > 0.2 or np.sign(pool) != np.sign(med))
            rows.append(row)
    return per_home, pd.DataFrame(rows)


def main():
    with stage_timer("s03_correlation") as log:
        cfg = main_config()
        comps = list(cfg.components)
        out = results_dir()
        allh = pd.read_parquet(WORK / "hourly_index_all.parquet")
        hourly = allh[allh.I.notna()]

        per_home, t3 = indicator_correlations(allh)
        write_table(per_home, out / "T3_corr_indicators_per_home.csv")
        write_table(t3, out / "T3_corr_indicators.csv")
        log.info("flags: %s", t3[t3.flag_spearman_pooled_vs_median | t3.flag_pearson_pooled_vs_median][["season", "x", "y"]].values.tolist())

        # Spearman I vs components per home and season
        rows = []
        for (home, season), g in hourly.groupby(["home", "season"]):
            if len(g) < MIN_COMMON:
                continue
            for c in comps:
                q = g[f"Q_{c}"]
                rows.append({"home": home, "season": season, "component": c, "n": len(g),
                             "spearman_I_Q": spearman(g.I, q) if q.nunique() > 1 else np.nan})
        iq = pd.DataFrame(rows)
        write_table(iq, out / "T3b_corr_index_components.csv")

        # Dominance S_c, formulas (8)-(9)
        flags = dominance_flags(hourly, cfg)
        fl = pd.concat([hourly.loc[flags.index, ["home", "season"]], flags], axis=1)
        fl["multi"] = flags.sum(axis=1) > 1

        def shares(g):
            r = {"N": len(g)}
            for c in comps:
                r[f"S_{c}"] = g[c].mean() if len(g) else np.nan
            r["share_multi"] = g["multi"].mean() if len(g) else np.nan
            return r

        rows = []
        for (home, season), g in fl.groupby(["home", "season"]):
            n_all = int(((hourly.home == home) & (hourly.season == season)).sum())
            rows.append({"level": "home_season", "home": home, "season": season, "n_hours_I": n_all, **shares(g)})
        for home, g in fl.groupby("home"):
            rows.append({"level": "home", "home": home, "season": "ALL", "n_hours_I": int((hourly.home == home).sum()), **shares(g)})
        for season, g in fl.groupby("season"):
            rows.append({"level": "pooled", "home": "ALL", "season": season, "n_hours_I": int((hourly.season == season).sum()), **shares(g)})
        rows.append({"level": "pooled", "home": "ALL", "season": "ALL", "n_hours_I": len(hourly), **shares(fl)})
        t5 = pd.DataFrame(rows)
        # median and IQR over homes
        cols = [f"S_{c}" for c in comps] + ["share_multi"]
        for lvl, season in [("home_season", "heating"), ("home_season", "warm"), ("home", "ALL")]:
            sub = t5[(t5.level == lvl) & (t5.season == season)]
            for stat, fn in [("median", lambda s: s.median()), ("q1", lambda s: s.quantile(.25)), ("q3", lambda s: s.quantile(.75))]:
                rows.append({"level": f"over_homes_{stat}", "home": f"n_homes={len(sub)}", "season": season,
                             "N": sub.N.median() if stat == "median" else np.nan,
                             **{c: fn(sub[c]) for c in cols}})
        t5 = pd.DataFrame(rows)
        write_table(t5, out / "T5_contribution.csv")
        log.info("\n%s", t5[t5.level.isin(["pooled"]) | t5.level.str.startswith("over")].to_string())


if __name__ == "__main__":
    main()
