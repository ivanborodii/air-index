"""Stage 11: data for result figures (figures_data/, ';' + decimal comma)
and draft PNGs (figures_draft/) -- task section 11."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import figures_data_dir, figures_draft_dir, read_table, results_dir, stage_timer, write_table

NAMES = ["EXCELLENT", "GOOD", "MODERATE", "LOW", "CRITICAL"]
ORDINAL = ["#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab", "#0d366b"]  # one-hue ramp, light -> dark = better -> worse
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.dpi": 200})


def stacked_classes(df, ax, title):
    left = np.zeros(len(df))
    for k, n in enumerate(NAMES):
        ax.barh(df.label, df[n], left=left, color=ORDINAL[k], edgecolor="#fcfcfb", linewidth=1, label=n)
        left += df[n].to_numpy()
    ax.set_xlim(0, 1)
    ax.set_title(title, color=INK, loc="left")
    ax.grid(axis="y", visible=False)


def main():
    with stage_timer("s11_figures") as log:
        out, fd, fg = results_dir(), figures_data_dir(), figures_draft_dir()

        # 1. classes of I by home and season
        cd = read_table(out / "T_class_distribution.csv")
        c = cd[(cd.scope == "home_season") & (cd.entity == "I")]
        fc = c.pivot_table(index=["home", "season"], columns="class", values="share").reindex(columns=NAMES).reset_index()
        write_table(fc, fd / "fig_classes_by_home.csv")
        fig, axes = plt.subplots(1, 2, figsize=(10, 7), sharey=True)
        for ax, s in zip(axes, ("heating", "warm")):
            d = fc[fc.season == s].assign(label=lambda x: x.home)
            stacked_classes(d, ax, f"Classes of I, {s} season (share of hours)")
        axes[1].legend(ncol=5, loc="upper center", bbox_to_anchor=(0, -0.05), frameon=False)
        fig.tight_layout()
        fig.savefig(fg / "fig_classes_by_home.png")
        plt.close(fig)

        # 2. dominance S_c by home and season
        t5 = read_table(out / "T5_contribution.csv")
        sc = t5[t5.level == "home_season"][["home", "season", "N", *[c for c in t5.columns if c.startswith("S_")], "share_multi"]]
        write_table(sc, fd / "fig_Sc_by_home.csv")
        scols = [c for c in sc.columns if c.startswith("S_")]
        fig, axes = plt.subplots(1, 2, figsize=(10, 7), sharey=True)
        for ax, s in zip(axes, ("heating", "warm")):
            d = sc[sc.season == s].reset_index(drop=True)
            y = np.arange(len(d))
            hgt = 0.8 / len(scols)
            for i, col in enumerate(scols):
                ax.barh(y + i * hgt, d[col], height=hgt, color=CAT[i], label=col)
            ax.set_yticks(y + 0.4 - hgt / 2, d.home)
            ax.set_xlim(0, 1)
            ax.set_title(f"Dominance shares S_c, {s} season", color=INK, loc="left")
            ax.grid(axis="y", visible=False)
        axes[1].legend(ncol=len(scols), loc="upper center", bbox_to_anchor=(0, -0.05), frameon=False)
        fig.tight_layout()
        fig.savefig(fg / "fig_Sc_by_home.png")
        plt.close(fig)

        # 3. horizons
        t2 = read_table(out / "T2_horizons.csv")
        hz = t2[t2.h.astype(str) != "episodes"].copy()
        hz["h"] = hz.h.astype(float).astype(int)
        cols = ["series", "h", "n_homes", "median_spearman", "median_pearson", "median_mae_persistence",
                "median_mae_same_hour_prev_day", "pooled_mae_persistence", "pooled_mae_same_hour_prev_day"]
        write_table(hz[cols], fd / "fig_horizons.csv")
        fig, ax = plt.subplots(figsize=(6, 4))
        for i, s in enumerate(hz.series.unique()):
            d = hz[hz.series == s]
            ax.plot(d.h, d.median_spearman, color=CAT[i], lw=2, marker="o", ms=5, label=s)
        ax.set_xticks([1, 3, 6, 12])
        ax.set_xlabel("horizon h, hours")
        ax.set_ylabel("median Spearman x(t), x(t+h)")
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(fg / "fig_horizons.png")
        plt.close(fig)

        # 4. aggregation rules
        t4 = read_table(out / "T4_aggregation_compare.csv")
        ag = t4[t4.season == "ALL"][["rule", "n_hours", *[f"share_{n}" for n in NAMES],
                                     "share_more_than_one_class_better_than_worst", "share_hides_LOW_CRITICAL"]]
        write_table(ag, fd / "fig_aggregation_compare.csv")
        d = ag.rename(columns={f"share_{n}": n for n in NAMES}).assign(label=lambda x: x.rule)
        fig, ax = plt.subplots(figsize=(8, 3))
        stacked_classes(d.iloc[::-1], ax, "Class distribution by aggregation rule")
        ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False)
        fig.tight_layout()
        fig.savefig(fg / "fig_aggregation_compare.png")
        plt.close(fig)

        # 5. MAE / macro-F1 by method
        t6, t7 = read_table(out / "T6_regression.csv"), read_table(out / "T7_classification.csv")
        f1 = t7.rename(columns={"source": "approach"})
        f1["approach"] = f1.approach.replace({"b": "b"})
        reg = t6[["scheme", "h", "method", "approach", "MAE", "RMSE", "MAE_home_median"]]
        cls = f1[["scheme", "h", "method", "approach", "macro_F1", "recall_CRITICAL", "recall_LOW_or_CRITICAL", "false_alarm_rate"]]
        mm = pd.concat([reg.assign(task="regression"), cls.assign(task="classification")], ignore_index=True)
        write_table(mm, fd / "fig_mae_by_method.csv")
        fig, axes = plt.subplots(2, 3, figsize=(12, 6), sharey="row")
        for j, h in enumerate(sorted(reg.h.unique())):
            for i, scheme in enumerate(("S1", "S2")):
                ax = axes[i, j]
                d = reg[(reg.scheme == scheme) & (reg.h == h)].sort_values("MAE")
                lab = d.method + " " + d.approach
                col = [CAT[0] if a == "a" else CAT[1] if a == "b" else "#9a9893" for a in d.approach]
                ax.barh(lab, d.MAE, color=col)
                ax.set_title(f"{scheme}, h = {h}: MAE of I", color=INK, loc="left")
                ax.grid(axis="y", visible=False)
                ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(fg / "fig_mae_by_method.png")
        plt.close(fig)

        # 6. example week
        wk = read_table(out / "F_example_week.csv")
        write_table(wk, fd / "fig_example_week.csv")
        wk["time"] = pd.to_datetime(wk.time)
        fig, ax = plt.subplots(figsize=(10, 3.5))
        ax.plot(wk.time, wk.I_actual, color=INK, lw=2, label="actual I")
        for i, h in enumerate((1, 3, 6)):
            ax.plot(wk.time, wk[f"I_forecast_h{h}"], color=CAT[i], lw=1.5, label=f"forecast h={h} ({wk[f'model_h{h}'].iloc[0]})")
        for y in (25, 50, 75):
            ax.axhline(y, color=INK2, lw=0.6, ls="--")
        ax.set_ylim(0, 100)
        ax.set_ylabel("I")
        ax.set_title(f"Example week, home {wk.home.iloc[0]} (S1 test period)", color=INK, loc="left")
        ax.legend(frameon=False, ncol=4, fontsize=8)
        fig.tight_layout()
        fig.savefig(fg / "fig_example_week.png")
        plt.close(fig)

        # 7. resources
        t9 = read_table(out / "T9_resources.csv")
        write_table(t9[["method", "approach", "h", "online_ms_per_point_mean", "online_ms_per_point_p95",
                        "feature_ms_per_point_mean", "model_bytes", "tuning_wall_s", "final_fit_wall_s",
                        "final_fit_mean_cores", "final_fit_peak_rss_mb", "online_peak_rss_mb"]], fd / "fig_resources.csv")
        rs = t9[t9.h == 3]
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
        lab = rs.method + " " + rs.approach
        axes[0].barh(lab, rs.online_ms_per_point_mean, color=CAT[0])
        axes[0].set_title("Forecast time per point, ms (incl. features), h = 3", color=INK, loc="left")
        axes[1].barh(lab, rs.model_bytes / 2**20, color=CAT[0])
        axes[1].set_xscale("log")
        axes[1].set_title("Model size, MiB (log scale)", color=INK, loc="left")
        for ax in axes:
            ax.grid(axis="y", visible=False)
        fig.tight_layout()
        fig.savefig(fg / "fig_resources.png")
        plt.close(fig)
        log.info("figures written to %s", fg)


if __name__ == "__main__":
    main()
