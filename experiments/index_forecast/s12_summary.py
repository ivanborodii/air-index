"""Stage 12: summary.json with the key numbers and stage durations."""

import json

import pandas as pd

from common import WORK, read_table, results_dir, stage_timer


def main():
    with stage_timer("s12_summary") as log:
        out = results_dir()
        s01 = json.loads((WORK / "s01_summary.json").read_text())
        s02 = json.loads((WORK / "s02_summary.json").read_text())
        merge = json.loads((WORK / "pm_merge_decision.json").read_text())
        t5b = read_table(out / "T5b_sensitivity.csv")
        base = t5b[t5b.variant == "base"]
        t6, t7 = read_table(out / "T6_regression.csv"), read_table(out / "T7_classification.csv")
        t4 = read_table(out / "T4_aggregation_compare.csv")
        t9 = read_table(out / "T9_resources.csv")
        tc = read_table(out / "T_text_check.csv")
        summ = {
            "dataset": s01, "index": s02, "pm_merge_rule": merge,
            "class_distribution_I_and_median_Sc": base.to_dict("records"),
            "aggregation_compare_all_hours": t4[t4.season == "ALL"].to_dict("records"),
            "forecast": {},
            "text_check": tc.to_dict("records"),
            "resources_h3": t9[t9.h == 3].to_dict("records"),
            "stage_times": json.loads((WORK / "stage_times.json").read_text()),
        }
        for scheme in ("S1", "S2"):
            for h in sorted(t6.h.unique()):
                r6 = t6[(t6.scheme == scheme) & (t6.h == h)]
                models = r6[r6.approach != "naive"].sort_values("MAE")
                naive = r6[r6.approach == "naive"].sort_values("MAE")
                r7 = t7[(t7.scheme == scheme) & (t7.h == h)]
                m7 = r7[r7.source != "naive"].sort_values("macro_F1", ascending=False)
                summ["forecast"][f"{scheme}_h{h}"] = {
                    "best_regression": models.iloc[0][["method", "approach", "MAE", "RMSE", "MAE_home_median"]].to_dict(),
                    "best_naive_regression": naive.iloc[0][["method", "MAE", "RMSE", "MAE_home_median"]].to_dict(),
                    "best_classification": m7.iloc[0][["method", "source", "macro_F1", "recall_CRITICAL", "recall_LOW_or_CRITICAL", "false_alarm_rate"]].to_dict(),
                    "naive_classification": r7[r7.source == "naive"][["method", "macro_F1", "recall_CRITICAL", "recall_LOW_or_CRITICAL", "false_alarm_rate"]].to_dict("records"),
                }
        (out / "summary.json").write_text(json.dumps(summ, indent=2, ensure_ascii=False, default=str))
        log.info("summary.json written")


if __name__ == "__main__":
    main()
