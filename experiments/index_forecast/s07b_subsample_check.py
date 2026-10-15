"""Stage 07b: cost of the training-row reduction (protocol.yaml).

Ridge and HGB, direct regression of I, scheme S1, h = 3: trained on all
training rows and on the protocol's fraction, same tuning procedure, same
test set. -> T_subsample_check.csv
"""

import json

import numpy as np
import pandas as pd

from common import WORK, results_dir, stage_timer, write_table
from models import ResourceMonitor, fit_model, inner_splits_s1, predict, split_masks, subsample_train, tune
from s07_forecast import PROTOCOL

H = 3


def main():
    with stage_timer("s07b_subsample_check") as log:
        fcols = json.loads((WORK / "features_info.json").read_text())["feature_columns"]
        feats = pd.read_parquet(WORK / "features.parquet")
        span = pd.read_csv(WORK / "time_cuts.csv", index_col=0, parse_dates=["min", "max", "cut"])
        homes = sorted(span.index)
        df = feats[feats[f"I__h{H}"].notna()].reset_index(drop=True)
        tr_full, te = split_masks(df, homes, homes, span, H)
        te &= df[f"I__h{H}_lag24"].notna().to_numpy()
        X = df[fcols].to_numpy(np.float32)
        y = df[f"I__h{H}"].to_numpy(float)
        rows = []
        for frac in (1.0, PROTOCOL["train_fraction"]):
            tr = subsample_train(df, tr_full, frac)
            splits = inner_splits_s1(df.loc[tr, "time"].to_numpy())
            for method in ("linear", "hgb"):
                with ResourceMonitor() as mon:
                    best, _ = tune(method, "reg", X[tr], y[tr], splits, (0, 100), subsample=PROTOCOL["tuning_subsample"])
                    est = fit_model(method, "reg", best, X[tr], y[tr])
                p = predict(est, "reg", X[te], (0, 100))
                e = p - y[te]
                ph = pd.DataFrame({"home": df.loc[te, "home"].to_numpy(), "ae": np.abs(e)}).groupby("home").ae.mean()
                rows.append({"method": method, "train_fraction": frac, "n_train": int(tr.sum()), "n_test": int(te.sum()),
                             "best_params": repr(best), "MAE": np.abs(e).mean(), "RMSE": np.sqrt((e ** 2).mean()),
                             "MAE_home_median": ph.median(), "wall_s_tuning_plus_fit": round(mon.wall_seconds, 1),
                             "peak_rss_mb": round(mon.peak_rss_mb, 1)})
                log.info("%s", rows[-1])
        t = pd.DataFrame(rows)
        full = t[t.train_fraction == 1.0].set_index("method").MAE
        t["MAE_change_vs_full_pct"] = 100 * (t.MAE / t.method.map(full) - 1)
        write_table(t, results_dir() / "T_subsample_check.csv")


if __name__ == "__main__":
    main()
