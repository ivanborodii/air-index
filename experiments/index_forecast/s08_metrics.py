"""Stage 08: metrics, statistics, example week, feature importance
(task section 9) -> T6, T7, T8, T_wilcoxon, T_hyperparams, F_*."""

import json

import joblib
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from sklearn.inspection import permutation_importance
from sklearn.metrics import confusion_matrix, f1_score

from common import HORIZONS_FORECAST, SEED, WORK, main_config, results_dir, stage_timer, write_table
from iaq_index.config import INDICATORS
from iaq_index.index import index_from_indicators
from iaq_index.scores import class_from_score
from models import METHODS, split_masks
from s07_forecast import MODEL_DIR, PRED_DIR, folds

NAMES = ["EXCELLENT", "GOOD", "MODERATE", "LOW", "CRITICAL"]
ALPHA = 0.05


def load_preds(scheme, h, method, target) -> pd.DataFrame | None:
    parts = sorted(PRED_DIR.glob(f"{scheme}_f*_h{h}_{method}_{target}.parquet"))
    n_folds = 1 if scheme == "S1" else 5
    if len(parts) != n_folds:
        return None
    return pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)


def reg_metrics(df: pd.DataFrame) -> dict:
    e = df.y_pred - df.y_true
    per_home = df.assign(ae=e.abs(), se=e ** 2).groupby("home").agg(mae=("ae", "mean"), mse=("se", "mean"))
    per_home["rmse"] = np.sqrt(per_home.mse)
    r = {"n_test": len(df), "MAE": e.abs().mean(), "RMSE": np.sqrt((e ** 2).mean()),
         "MAE_home_median": per_home.mae.median(), "MAE_home_q1": per_home.mae.quantile(.25),
         "MAE_home_q3": per_home.mae.quantile(.75), "RMSE_home_median": per_home.rmse.median(),
         "RMSE_home_q1": per_home.rmse.quantile(.25), "RMSE_home_q3": per_home.rmse.quantile(.75)}
    for s, g in df.groupby("season"):
        eg = g.y_pred - g.y_true
        r[f"MAE_{s}"], r[f"RMSE_{s}"] = eg.abs().mean(), np.sqrt((eg ** 2).mean())
    return r, per_home.mae


def clf_metrics(y, p) -> tuple[dict, np.ndarray]:
    y, p = np.asarray(y, int), np.asarray(p, int)
    cm = confusion_matrix(y, p, labels=list(range(5)))
    good = y <= 2
    r = {"n_test": len(y), "macro_F1": f1_score(y, p, labels=list(range(5)), average="macro", zero_division=0),
         "recall_CRITICAL": np.mean(p[y == 4] == 4) if (y == 4).any() else np.nan,
         "recall_LOW_or_CRITICAL": np.mean(p[y >= 3] >= 3) if (y >= 3).any() else np.nan,
         "false_alarm_rate": np.mean(p[good] >= 3) if good.any() else np.nan,
         "n_false_alarms": int((good & (p >= 3)).sum()), "n_pred_LOW_or_CRITICAL": int((p >= 3).sum())}
    for k in range(5):
        r[f"n_test_{NAMES[k]}"] = int((y == k).sum())
    return r, cm


def holm(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    ok = ~np.isnan(p)
    adj = np.full_like(p, np.nan)
    idx = np.argsort(p[ok])
    m = ok.sum()
    vals = np.minimum(1, np.maximum.accumulate((m - np.arange(m)) * p[ok][idx]))
    tmp = np.empty(m)
    tmp[idx] = vals
    adj[ok] = tmp
    return adj


def main():
    with stage_timer("s08_metrics") as log:
        cfg = main_config()
        out = results_dir()
        info = json.loads((WORK / "features_info.json").read_text())
        fcols = info["feature_columns"]
        feats = pd.read_parquet(WORK / "features.parquet")
        span = pd.read_csv(WORK / "time_cuts.csv", index_col=0, parse_dates=["min", "max", "cut"])
        homes = sorted(span.index)
        comps = list(cfg.components)

        reg_rows, clf_rows, t8_rows, cm_rows, wil_rows, cnt_rows = [], [], [], [], [], []
        home_mae = {}  # (scheme, h, model) -> per-home MAE series
        for scheme in ("S1", "S2"):
            for h in HORIZONS_FORECAST:
                df = feats[feats[f"I__h{h}"].notna()].reset_index(drop=True)
                key = df[["home", "time"]]
                # class counts in training and test (pooled over folds)
                tr_cls, te_rows = [], []
                for fold, htr, hte in folds(scheme, homes):
                    tr, te = split_masks(df, htr, hte, span, h)
                    te &= df[f"I__h{h}_lag24"].notna().to_numpy()
                    tr_cls.append(class_from_score(df.loc[tr, f"I__h{h}"].to_numpy()))
                    te_rows.append(np.flatnonzero(te))
                trc = np.concatenate(tr_cls)
                test = df.iloc[np.concatenate(te_rows)].copy()
                yc = class_from_score(test[f"I__h{h}"].to_numpy())
                # training counts are summed over the folds (S2: 5 folds, each home trains in 4)
                cnt = {"scheme": scheme, "h": h, "n_folds": len(tr_cls)}
                for k in range(5):
                    cnt[f"train_{NAMES[k]}"] = int((trc == k).sum())
                    cnt[f"test_{NAMES[k]}"] = int((yc == k).sum())
                cnt["test_CRITICAL_lt_30"] = bool((yc == 4).sum() < 30)
                cnt_rows.append(cnt)

                base = test[["home", "time", "season"]].copy()
                base["y_true"] = test[f"I__h{h}"].to_numpy()
                preds = {"naive_persistence": test["I"].to_numpy(dtype=float),
                         "naive_same_hour_prev_day": test[f"I__h{h}_lag24"].to_numpy(dtype=float)}
                clf_preds = {k: class_from_score(v) for k, v in preds.items()}
                dom_match = {}
                for method in METHODS:
                    a = load_preds(scheme, h, method, "reg_I")
                    if a is not None:
                        a = base[["home", "time"]].merge(a, on=["home", "time"], how="left", validate="one_to_one")
                        preds[f"{method}|a"] = a.y_pred.to_numpy()
                        clf_preds[f"{method}|a_from_reg"] = class_from_score(np.clip(a.y_pred.to_numpy(), 0, 100))
                    c = load_preds(scheme, h, method, "clf_I")
                    if c is not None:
                        c = base[["home", "time"]].merge(c, on=["home", "time"], how="left", validate="one_to_one")
                        clf_preds[f"{method}|a_classifier"] = c.y_pred.to_numpy()
                    inds = {x: load_preds(scheme, h, method, f"ind_{x}") for x in INDICATORS}
                    if all(v is not None for v in inds.values()):
                        vals = {x: base[["home", "time"]].merge(v, on=["home", "time"], how="left")["y_pred"].to_numpy()
                                for x, v in inds.items()}
                        fr = index_from_indicators(vals, cfg)
                        preds[f"{method}|b"] = fr["I"].to_numpy()
                        clf_preds[f"{method}|b"] = fr["class_I"].to_numpy()
                        # dominant component: forecast argmax vs actual (tolerance 1), hours with actual I > 25
                        qf = fr[[f"Q_{c}" for c in comps]].to_numpy()
                        qa = test[[f"Q_{c}__h{h}" for c in comps]].to_numpy()
                        qa_max = test[f"Q_max__h{h}"].to_numpy()
                        sel = base.y_true.to_numpy() > cfg.dominance_min_index
                        hit = qa[np.arange(len(qa)), qf.argmax(axis=1)] >= qa_max - cfg.dominance_tolerance
                        dom_match[method] = (float(hit[sel].mean()), int(sel.sum()))

                for model, p in preds.items():
                    if np.isnan(p).any():
                        log.warning("%s %s h%d: %d NaN predictions", scheme, model, h, np.isnan(p).sum())
                    m, ph = reg_metrics(base.assign(y_pred=p))
                    meth, appr = model.split("|") if "|" in model else (model, "naive")
                    reg_rows.append({"scheme": scheme, "h": h, "method": meth, "approach": appr, **m})
                    home_mae[(scheme, h, model)] = ph
                for model, p in clf_preds.items():
                    meth, src = model.split("|") if "|" in model else (model, "naive")
                    m, cm = clf_metrics(base.y_true.pipe(class_from_score), p)
                    clf_rows.append({"scheme": scheme, "h": h, "method": meth, "source": src, **m})
                    for i in range(5):
                        for j in range(5):
                            cm_rows.append({"scheme": scheme, "h": h, "method": meth, "source": src,
                                            "actual": NAMES[i], "predicted": NAMES[j], "n": int(cm[i, j])})

                # Wilcoxon on per-home MAE, Holm within (scheme, h)
                naive = {k: base.assign(y_pred=preds[k]).pipe(lambda d: (d.y_pred - d.y_true).abs().mean())
                         for k in ("naive_persistence", "naive_same_hour_prev_day")}
                best_naive = min(naive, key=naive.get)
                tests = []
                for model in preds:
                    if model.startswith("naive"):
                        continue
                    tests.append(("model_vs_best_naive", model, best_naive))
                for method in METHODS:
                    if f"{method}|a" in preds and f"{method}|b" in preds:
                        tests.append(("approach_a_vs_b", f"{method}|a", f"{method}|b"))
                fam = []
                for kind, m1, m2 in tests:
                    x1, x2 = home_mae[(scheme, h, m1)], home_mae[(scheme, h, m2)]
                    x1, x2 = x1.align(x2, join="inner")
                    d = x1 - x2
                    p = wilcoxon(x1, x2).pvalue if (d != 0).any() else 1.0
                    fam.append({"scheme": scheme, "h": h, "comparison": kind, "model_1": m1, "model_2": m2,
                                "n_homes": len(d), "median_MAE_1": x1.median(), "median_MAE_2": x2.median(),
                                "median_diff": d.median(), "n_homes_1_better": int((d < 0).sum()), "p_value": p})
                adj = holm(np.array([r["p_value"] for r in fam]))
                for r, a in zip(fam, adj):
                    r["p_holm"] = a
                    r["significant_holm_0.05"] = bool(a < ALPHA)
                wil_rows += fam

                for method in METHODS:
                    if f"{method}|a" not in preds or f"{method}|b" not in preds:
                        continue
                    ra = next(r for r in reg_rows if r["scheme"] == scheme and r["h"] == h and r["method"] == method and r["approach"] == "a")
                    rb = next(r for r in reg_rows if r["scheme"] == scheme and r["h"] == h and r["method"] == method and r["approach"] == "b")
                    ca = next((r for r in clf_rows if r["scheme"] == scheme and r["h"] == h and r["method"] == method and r["source"] == "a_from_reg"), {})
                    cc = next((r for r in clf_rows if r["scheme"] == scheme and r["h"] == h and r["method"] == method and r["source"] == "a_classifier"), {})
                    cb = next((r for r in clf_rows if r["scheme"] == scheme and r["h"] == h and r["method"] == method and r["source"] == "b"), {})
                    w = next(r for r in wil_rows if r["scheme"] == scheme and r["h"] == h and r["comparison"] == "approach_a_vs_b" and r["model_1"] == f"{method}|a")
                    t8_rows.append({"scheme": scheme, "h": h, "method": method,
                                    "MAE_a_direct": ra["MAE"], "MAE_b_indicators": rb["MAE"],
                                    "RMSE_a_direct": ra["RMSE"], "RMSE_b_indicators": rb["RMSE"],
                                    "MAE_home_median_a": ra["MAE_home_median"], "MAE_home_median_b": rb["MAE_home_median"],
                                    "macroF1_a_classifier": cc.get("macro_F1"), "macroF1_a_from_reg": ca.get("macro_F1"),
                                    "macroF1_b": cb.get("macro_F1"),
                                    "recallCRIT_a_classifier": cc.get("recall_CRITICAL"), "recallCRIT_a_from_reg": ca.get("recall_CRITICAL"),
                                    "recallCRIT_b": cb.get("recall_CRITICAL"),
                                    "b_dominant_component_match_share": dom_match.get(method, (np.nan, 0))[0],
                                    "b_dominant_n_hours_I_gt_25": dom_match.get(method, (np.nan, 0))[1],
                                    "wilcoxon_p_a_vs_b": w["p_value"], "wilcoxon_p_holm": w["p_holm"]})
                if scheme == "S1":
                    pd.DataFrame({**{"home": base.home, "time": base.time, "season": base.season, "y_true": base.y_true},
                                  **{k: v for k, v in preds.items()}}).to_parquet(WORK / f"S1_h{h}_all_preds.parquet", index=False)

        t6, t7 = pd.DataFrame(reg_rows), pd.DataFrame(clf_rows)
        write_table(t6, out / "T6_regression.csv")
        write_table(t7, out / "T7_classification.csv")
        write_table(pd.DataFrame(cm_rows), out / "T7b_confusion_matrices.csv")
        write_table(pd.DataFrame(cnt_rows), out / "T7c_class_counts_train_test.csv")
        write_table(pd.DataFrame(t8_rows), out / "T8_direct_vs_indicators.csv")
        write_table(pd.DataFrame(wil_rows), out / "T_wilcoxon.csv")
        hyperparams(out)
        example_week(t6, out, log)
        feature_importance(t6, feats, fcols, span, homes, out, log)


def hyperparams(out):
    rows = []
    for p in sorted(PRED_DIR.glob("*.json")):
        m = json.loads(p.read_text())
        rows.append({k: m[k] for k in ("scheme", "fold", "h", "method", "target", "search_space", "best_params",
                                       "train_fraction", "tuning_subsample", "tuning_seconds", "final_fit_seconds", "n_train", "n_test")}
                    | {"cv_scores": "; ".join(f"{r['params']}={r['cv_score']:.4f}" for r in m["cv_scores"])})
    write_table(pd.DataFrame(rows), out / "T_hyperparams.csv")


def best_model(t6, scheme, h) -> str:
    sub = t6[(t6.scheme == scheme) & (t6.h == h) & (t6.approach != "naive")]
    r = sub.loc[sub.MAE.idxmin()]
    return f"{r.method}|{r.approach}"


def example_week(t6, out, log):
    """Test home of S1 with the highest standard deviation of I in its test
    period; the 7-day window (168 h) of that home's test period with the
    highest std of actual I. Forecasts of the best S1 model per h."""
    frames = {h: pd.read_parquet(WORK / f"S1_h{h}_all_preds.parquet") for h in HORIZONS_FORECAST}
    f1 = frames[1]
    home = f1.groupby("home").y_true.std().idxmax()
    s = f1[f1.home == home].set_index("time").y_true.asfreq("1h")
    roll = s.rolling("168h", min_periods=120).std()
    end = roll.idxmax()
    start = end - pd.Timedelta(hours=167)
    week = pd.DataFrame({"time": pd.date_range(start, end, freq="1h")})
    week["home"] = home
    week = week.merge(f1[f1.home == home][["time", "y_true"]].rename(columns={"y_true": "I_actual"}), on="time", how="left")
    choice = {}
    for h, fr in frames.items():
        bm = best_model(t6, "S1", h)
        choice[h] = bm
        # forecast issued at t for t+h, plotted at the target time t+h
        f = fr[fr.home == home][["time", bm]].assign(time=lambda d: d.time + pd.Timedelta(hours=h))
        week = week.merge(f.rename(columns={bm: f"I_forecast_h{h}"}), on="time", how="left")
        week[f"model_h{h}"] = bm
    write_table(week, out / "F_example_week.csv")
    (WORK / "example_week_choice.json").write_text(json.dumps(
        {"home": home, "start": str(start), "end": str(end), "best_models": choice,
         "rule": "S1 test home with the highest std of actual I; 168-h window with the highest rolling std (>=120 h present); forecasts plotted at target time t+h"}, indent=2))
    log.info("example week: %s %s..%s %s", home, start, end, choice)


def feature_importance(t6, feats, fcols, span, homes, out, log):
    """Permutation importance (MAE) of the best S1 direct model at h = 3 on a
    random 5000-row sample of its test set (seed 42), 5 repeats."""
    h = 3
    sub = t6[(t6.scheme == "S1") & (t6.h == h) & (t6.approach == "a")]
    method = sub.loc[sub.MAE.idxmin(), "method"]
    est = joblib.load(MODEL_DIR / f"S1_f0_h{h}_{method}_reg_I.joblib")
    df = feats[feats[f"I__h{h}"].notna()].reset_index(drop=True)
    _, te = split_masks(df, homes, homes, span, h)
    te &= df[f"I__h{h}_lag24"].notna().to_numpy()
    idx = np.random.default_rng(SEED).choice(np.flatnonzero(te), size=min(5000, te.sum()), replace=False)
    X = df.loc[idx, fcols].to_numpy(np.float32)
    y = df.loc[idx, f"I__h{h}"].to_numpy()
    r = permutation_importance(est, X, y, scoring="neg_mean_absolute_error", n_repeats=5, random_state=SEED, n_jobs=1)
    fi = pd.DataFrame({"feature": fcols, "importance_mean_MAE_increase": r.importances_mean,
                       "importance_std": r.importances_std}).sort_values("importance_mean_MAE_increase", ascending=False)
    fi.insert(0, "rank", range(1, len(fi) + 1))
    fi["model"] = f"S1 h={h} {method} direct regression"
    write_table(fi.head(20), out / "F_feature_importance.csv")
    log.info("feature importance for %s:\n%s", method, fi.head(10).to_string())


if __name__ == "__main__":
    main()
