"""Stage 06: causal features z(t) and targets for h = 1, 3, 6 (task 7, 8.1)."""

import json

import numpy as np
import pandas as pd

from common import HORIZONS_FORECAST, WORK, main_config, stage_timer
from iaq_index.config import INDICATORS
from iaq_index.features import add_targets, build_features, feature_columns


def main():
    with stage_timer("s06_features") as log:
        cfg = main_config()
        comps = [f"Q_{c}" for c in cfg.components]
        allh = pd.read_parquet(WORK / "hourly_index_all.parquet")
        feats = build_features(allh, comps)
        tgt_cols = ["I", "Q_max", *comps, *INDICATORS]
        targets = add_targets(allh[["home", "time", "season", *tgt_cols]], HORIZONS_FORECAST, tgt_cols)
        keep = ["home", "time", "season"] + [c for c in targets.columns if "__h" in c]
        df = feats.merge(targets[keep], on=["home", "time"], how="left", validate="one_to_one")
        fcols = feature_columns(comps)
        df[fcols] = df[fcols].astype(np.float32)
        df.to_parquet(WORK / "features.parquet", index=False)
        info = {"n_hours_with_I": int(allh.I.notna().sum()), "n_feature_rows": len(df), "n_features": len(fcols),
                "feature_columns": fcols}
        for h in HORIZONS_FORECAST:
            info[f"n_target_available_h{h}"] = int(df[f"I__h{h}"].notna().sum())
            info[f"n_target_and_lag24_h{h}"] = int((df[f"I__h{h}"].notna() & df[f"I__h{h}_lag24"].notna()).sum())
        (WORK / "features_info.json").write_text(json.dumps(info, indent=2))
        log.info("%s", {k: v for k, v in info.items() if k != "feature_columns"})


if __name__ == "__main__":
    main()
