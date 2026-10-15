"""Stage 09: resource use on the Raspberry Pi 5 (task 9.4).

T9_resources.csv          one row per S1 model set (method x approach x h):
                          training cost (tuning + final fit) and online
                          forecasting cost measured here.
T9b_resources_all_units   every trained unit of S1 and S2 (tuning, final fit
                          and batch test prediction, from stage 07).
T9c_resources_by_method   total compute per method over the whole experiment.

Online forecasting is measured for 1000 random test time points (seed 42)
of the S1 test set. Per point the timer covers slicing the last 24 h of
raw indicators, scoring the current hour with formulas (1)-(7), building
z(t) (NumPy path, tested equal to the batch features) and predicting
(approach (b): 5 indicator models + formulas (1)-(7)). Models are loaded
from disk first; load time and the RSS increase are recorded too.
"""

import gc
import json
import time

import joblib
import numpy as np
import pandas as pd
import psutil

from common import SEED, WORK, main_config, results_dir, stage_timer, write_table
from iaq_index.config import INDICATORS
from iaq_index.features import features_at_fast
from iaq_index.index import compute_index_frame, index_from_indicators
from models import METHODS, ResourceMonitor
from s07_forecast import MODEL_DIR, PRED_DIR

N_POINTS = 1000
APPROACHES = {"a_regression": ["reg_I"], "a_classifier": ["clf_I"], "b_indicators": [f"ind_{x}" for x in INDICATORS]}


def load_meta() -> pd.DataFrame:
    return pd.DataFrame([json.loads(p.read_text()) for p in sorted(PRED_DIR.glob("*.json"))])


def main():
    with stage_timer("s09_resources") as log:
        cfg = main_config()
        comps = [f"Q_{c}" for c in cfg.components]
        out = results_dir()
        grid = pd.read_parquet(WORK / "hourly_index_all.parquet", columns=["home", "time", "season", *INDICATORS])
        arrays = {h: (g.time.to_numpy(), g[INDICATORS].to_numpy(float), g.season.to_numpy())
                  for h, g in grid.groupby("home")}
        meta = load_meta()

        def z_of(home, t):
            times, vals, season = arrays[home]
            hi = np.searchsorted(times, t.to_datetime64(), side="right")
            lo = np.searchsorted(times, (t - pd.Timedelta(hours=24)).to_datetime64(), side="right")
            cur = compute_index_frame(pd.DataFrame(vals[hi - 1:hi], columns=INDICATORS), cfg)[[*comps, "I"]].iloc[0].to_dict()
            z = features_at_fast(times[lo:hi], vals[lo:hi], cur, t, int(season[hi - 1] == "heating"), comps)
            return z.astype(np.float32).reshape(1, -1)

        rows = []
        for h in (1, 3, 6):
            test = pd.read_parquet(PRED_DIR / f"S1_f0_h{h}_linear_reg_I.parquet")[["home", "time"]]
            pts = test.sample(n=N_POINTS, random_state=SEED).reset_index(drop=True)
            pts_list = list(zip(pts.home, pts.time))
            lat = []
            for home, t in pts_list:  # features alone, reference for all models at this h
                t0 = time.perf_counter()
                z_of(home, t)
                lat.append(time.perf_counter() - t0)
            feat_ms = 1000 * np.mean(lat)
            for method in METHODS:
                for approach, tgs in APPROACHES.items():
                    paths = [MODEL_DIR / f"S1_f0_h{h}_{method}_{tg}.joblib" for tg in tgs]
                    if not all(p.exists() for p in paths):
                        continue
                    gc.collect()
                    rss0 = psutil.Process().memory_info().rss
                    t0 = time.perf_counter()
                    models = {tg: joblib.load(p) for tg, p in zip(tgs, paths)}
                    load_s = time.perf_counter() - t0
                    rss_loaded = psutil.Process().memory_info().rss
                    z0 = z_of(*pts_list[0])
                    for est in models.values():  # warm-up: thread pools, lazy init
                        est.predict(z0)
                    lat = []
                    with ResourceMonitor(interval=0.1) as mon:
                        for home, t in pts_list:
                            t0 = time.perf_counter()
                            z = z_of(home, t)
                            if approach == "b_indicators":
                                index_from_indicators({x: models[f"ind_{x}"].predict(z) for x in INDICATORS}, cfg)
                            else:
                                models[tgs[0]].predict(z)
                            lat.append(time.perf_counter() - t0)
                    lat = 1000 * np.array(lat)
                    sel = meta[(meta.scheme == "S1") & (meta.h == h) & (meta.method == method) & meta.target.isin(tgs)]
                    rows.append({
                        "method": method, "approach": approach, "h": h, "n_models": len(tgs),
                        "n_train_rows": int(sel.n_train.iloc[0]),
                        "train_fraction": sel.train_fraction.iloc[0], "tuning_subsample": sel.tuning_subsample.iloc[0],
                        "best_params": " | ".join(sel.best_params),
                        "tuning_wall_s": sel.tune_wall_s.sum(), "tuning_cpu_s": sel.tune_cpu_s.sum(),
                        "final_fit_wall_s": sel.fit_wall_s.sum(), "final_fit_cpu_s": sel.fit_cpu_s.sum(),
                        "final_fit_mean_cores": round(sel.fit_cpu_s.sum() / max(sel.fit_wall_s.sum(), 1e-9), 2),
                        "final_fit_peak_cores": sel.fit_peak_cores.max(),
                        "final_fit_peak_rss_mb": sel.fit_peak_rss_mb.max(), "tuning_peak_rss_mb": sel.tune_peak_rss_mb.max(),
                        "final_fit_temp_max_c": sel.fit_temp_max_c.max(), "final_fit_min_freq_mhz": sel.fit_min_freq_mhz.min(),
                        "model_bytes": int(sum(p.stat().st_size for p in paths)),
                        "model_load_s": round(load_s, 3), "model_rss_increase_mb": round((rss_loaded - rss0) / 2**20, 1),
                        "batch_predict_us_per_row": sel.test_predict_us_per_row.sum(),
                        "online_ms_per_point_mean": lat.mean(), "online_ms_per_point_median": np.median(lat),
                        "online_ms_per_point_p95": np.percentile(lat, 95), "online_ms_per_point_max": lat.max(),
                        "feature_ms_per_point_mean": feat_ms,
                        "online_cpu_s_per_point": mon.cpu_seconds / N_POINTS, "online_mean_cores": mon.mean_cores,
                        "online_peak_rss_mb": mon.peak_rss_mb, "online_temp_start_c": mon.temp_start_c,
                        "online_temp_end_c": mon.temp_end_c, "online_min_freq_mhz": mon.min_freq_mhz,
                    })
                    del models
                    log.info("h=%d %s %s: %.2f ms/point", h, method, approach, lat.mean())
        write_table(pd.DataFrame(rows), out / "T9_resources.csv")

        keep = [c for c in meta.columns if c not in ("cv_scores", "search_space", "task", "finished")]
        write_table(meta[keep].sort_values(["scheme", "h", "method", "target", "fold"]), out / "T9b_resources_all_units.csv")
        meta["total_wall_s"] = meta.tune_wall_s + meta.fit_wall_s + meta.predict_wall_s
        meta["total_cpu_s"] = meta.tune_cpu_s + meta.fit_cpu_s + meta.predict_cpu_s
        by = meta.groupby("method").agg(
            n_units=("target", "size"), total_wall_h=("total_wall_s", lambda s: s.sum() / 3600),
            total_cpu_h=("total_cpu_s", lambda s: s.sum() / 3600),
            tuning_wall_h=("tune_wall_s", lambda s: s.sum() / 3600), final_fit_wall_h=("fit_wall_s", lambda s: s.sum() / 3600),
            mean_final_fit_s=("fit_wall_s", "mean"), max_final_fit_s=("fit_wall_s", "max"),
            peak_rss_mb=("fit_peak_rss_mb", "max"), max_temp_c=("fit_temp_max_c", "max"),
            min_freq_mhz=("fit_min_freq_mhz", "min"), mean_model_bytes_S1=("model_bytes", "mean")).reset_index()
        by["mean_cores"] = by.total_cpu_h / by.total_wall_h
        by["share_of_total_wall"] = by.total_wall_h / by.total_wall_h.sum()
        write_table(by, out / "T9c_resources_by_method.csv")
        log.info("\n%s", by.to_string())


if __name__ == "__main__":
    main()
