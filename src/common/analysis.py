"""
Analysis Pipeline
==================

Paper reference: Section 5 — Statistical Analysis; Tables 2-4, Figures 2-5

This module wraps the full analyze_results.py logic as a callable function
`run_analysis(output_dir)` so that run.py can invoke it directly instead of
via subprocess.

ALL analysis logic is verbatim from scripts/analyze_results.py — no
algorithmic changes. The original file is retained as a standalone entry
point for backward compatibility.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

warnings.filterwarnings("ignore")

from src.managing_system.analyse.fault_classifier import get_uncertainty_class


# ---------------------------------------------------------------------------
# Statistical helpers (verbatim from analyze_results.py)
# ---------------------------------------------------------------------------

def bootstrap_ci(data, n_boot: int = 1000, ci: int = 95):
    """Bootstrap confidence interval for the mean (verbatim from analyze_results.py L19-30)."""
    if len(data) < 2:
        m = np.mean(data) if len(data) == 1 else 0.0
        return m, m, m
    boot_means = []
    for _ in range(n_boot):
        sample = np.random.choice(data, size=len(data), replace=True)
        boot_means.append(np.mean(sample))
    lower = np.percentile(boot_means, (100 - ci) / 2)
    upper = np.percentile(boot_means, 100 - (100 - ci) / 2)
    return np.mean(data), lower, upper


def wilcoxon_test(x, y, label: str = ""):
    """Wilcoxon signed-rank test with rank-biserial effect size (verbatim from analyze_results.py L33-53)."""
    x = np.array(x, dtype=float)
    y = np.array(y, dtype=float)
    diffs = x - y
    nonzero_mask = diffs != 0
    if nonzero_mask.sum() < 5:
        return {"test": label, "W": None, "p": None, "effect_r": None,
                "note": f"Too few non-zero differences ({nonzero_mask.sum()})"}
    try:
        stat, p = wilcoxon(x[nonzero_mask], y[nonzero_mask])
        n = nonzero_mask.sum()
        effect_r = 1.0 - (2.0 * stat) / (n * (n + 1) / 2.0)
        return {"test": label, "W": stat, "p": round(p, 4), "effect_r": round(effect_r, 3), "n": n}
    except Exception as e:
        return {"test": label, "W": None, "p": None, "effect_r": None, "note": str(e)}


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def run_analysis(output_dir: str = "results") -> None:
    """
    Run the full analysis pipeline on existing trial_summary.csv and
    raw_episodes.jsonl in output_dir.

    Produces:
      aggregate_by_class.csv, statistical_tests.csv, confidence_intervals.csv,
      multi_scale_breakdown.csv, per_scenario_breakdown.csv,
      paper_tables.tex, figures/fig_*.pdf/.png, analysis_report.txt

    Verbatim from: scripts/analyze_results.py run_analysis() (L56-557).
    """
    out_path = Path(output_dir)
    summary_file = out_path / "trial_summary.csv"
    raw_file = out_path / "raw_episodes.jsonl"

    if not summary_file.exists():
        print(f"Error: {summary_file} not found. Run the experiment first.")
        return

    df = pd.read_csv(summary_file)
    df["uncertainty_class"] = df["scenario"].apply(get_uncertainty_class)

    raw_records = []
    with open(raw_file) as f:
        for line in f:
            raw_records.append(json.loads(line.strip()))
    df_raw = pd.DataFrame(raw_records)

    report_lines = ["=== DIGITAL TWIN SA/DT PIPELINE ANALYSIS (WITH STATISTICAL TESTS) ===", ""]

    df["episodes_to_recover_valid"] = df["episodes_to_recover"].replace(-1, np.nan)

    # 1. Cumulative aggregate table
    agg = df.groupby(["mode", "uncertainty_class"]).agg({
        "episodes_to_recover_valid": ["mean", "std", "count"],
        "episode_success": ["mean", "std"],
        "mean_cost": ["mean", "std"],
        "integrated_risk": ["mean", "std"],
        "mean_risk_drift": ["mean", "std"],
    }).reset_index()
    agg.columns = [
        "mode", "uncertainty_class",
        "recovery_mean", "recovery_std", "recovery_n",
        "success_mean", "success_std",
        "cost_mean", "cost_std",
        "ire_mean", "ire_std",
        "drift_mean", "drift_std",
    ]
    reactive_costs = agg[agg["mode"] == "reactive"].set_index("uncertainty_class")["cost_mean"]
    def calc_savings(row):
        base_c = reactive_costs.get(row["uncertainty_class"], 0)
        return ((base_c - row["cost_mean"]) / base_c * 100.0) if base_c > 0 else 0.0
    agg["cost_savings_%"] = agg.apply(calc_savings, axis=1)
    agg.to_csv(out_path / "aggregate_by_class.csv", index=False)

    # 2. Statistical tests
    stat_results = []
    has_scale = "scale_days" in df.columns
    group_cols = ["scale_days", "scenario", "trial_seed"] if has_scale else ["scenario", "trial_seed"]
    for metric in ["episode_success", "integrated_risk", "episodes_to_recover_valid"]:
        for uc in ["epistemic", "aleatoric"]:
            df_uc = df[df["uncertainty_class"] == uc]
            for baseline, label_prefix in [("reactive", "SA-DT vs Reactive"), ("sa_only", "SA-DT vs SA-Only")]:
                df_base = df_uc[df_uc["mode"] == baseline][group_cols + [metric]].rename(columns={metric: "baseline"})
                df_dt   = df_uc[df_uc["mode"] == "sa_dt"][group_cols + [metric]].rename(columns={metric: "sa_dt"})
                merged = df_base.merge(df_dt, on=group_cols, how="inner").dropna()
                if len(merged) >= 5:
                    result = wilcoxon_test(merged["sa_dt"].values, merged["baseline"].values,
                                           f"{label_prefix} | {uc} | {metric}")
                else:
                    result = {"test": f"{label_prefix} | {uc} | {metric}",
                              "W": None, "p": None, "effect_r": None,
                              "note": f"Insufficient paired samples ({len(merged)})"}
                stat_results.append(result)
    df_stats = pd.DataFrame(stat_results)
    df_stats.to_csv(out_path / "statistical_tests.csv", index=False)

    report_lines.append("--- Statistical Tests (Wilcoxon Signed-Rank) ---")
    for _, row in df_stats.iterrows():
        if row["p"] is not None:
            sig = "***" if row["p"] < 0.001 else "**" if row["p"] < 0.01 else "*" if row["p"] < 0.05 else "ns"
            report_lines.append(f"  {row['test']}: W={row['W']}, p={row['p']} {sig}, r={row['effect_r']}")
        else:
            report_lines.append(f"  {row['test']}: SKIPPED ({row.get('note', 'N/A')})")
    report_lines.append("")

    # 3. Bootstrap CIs
    ci_data = []
    for mode in ["reactive", "sa_only", "sa_dt"]:
        for uc in ["epistemic", "aleatoric"]:
            subset = df[(df["mode"] == mode) & (df["uncertainty_class"] == uc)]
            if subset.empty:
                continue
            for metric in ["episode_success", "integrated_risk", "episodes_to_recover_valid"]:
                vals = subset[metric].dropna().values
                if len(vals) > 0:
                    mean, lo, hi = bootstrap_ci(vals)
                    ci_data.append({"mode": mode, "class": uc, "metric": metric,
                                    "mean": round(mean, 3), "ci_lo": round(lo, 3), "ci_hi": round(hi, 3)})
    pd.DataFrame(ci_data).to_csv(out_path / "confidence_intervals.csv", index=False)

    # 4. Proactiveness
    proactive_data = []
    for mode in ["reactive", "sa_only", "sa_dt"]:
        df_m = df[df["mode"] == mode]
        if not df_m.empty:
            proactive_rate = (len(df_m[df_m["proactive_count"] > 0]) / len(df_m)) * 100.0
            mean_lead = df_m["lead_time"].mean()
            proactive_data.append({"mode": mode,
                                   "proactive_rate_%": round(proactive_rate, 2),
                                   "mean_lead_time_eps": round(mean_lead, 2)})
    tab_proactive = pd.DataFrame(proactive_data)

    # 5. Accuracy / routing consistency
    acc_data = []
    for mode in ["reactive", "sa_only", "sa_dt"]:
        df_m = df_raw[df_raw["mode"] == mode]
        if not df_m.empty:
            routing_vals = df_m["routing_correct"].dropna()
            routing_acc = routing_vals.mean() * 100 if len(routing_vals) > 0 else float("nan")
            top1 = df_m["is_top1"].mean() * 100
            lag = df_m["lag_seconds"].mean()
            acc_data.append({"mode": mode,
                             "routing_consistency_%": round(routing_acc, 1),
                             "top1_align_%": round(top1, 1),
                             "mean_sync_lag_s": round(lag, 2)})
    tab_acc = pd.DataFrame(acc_data)

    # 6. Latency (unconditional + conditioned)
    lat_data = []
    for mode in ["reactive", "sa_only", "sa_dt"]:
        df_m = df_raw[df_raw["mode"] == mode]
        if not df_m.empty:
            t_m = df_m["t_m"].mean()
            t_p = df_m["t_p"].mean()
            t_e = df_m["t_e"].mean()
            total = t_m + t_p + t_e
            df_actuated = df_m[~df_m["candidate_selected"].isin([None, "C5", "None"])]
            t_e_cond = df_actuated["t_e"].mean() if len(df_actuated) > 0 else 0.0
            total_cond = t_m + t_p + t_e_cond
            n_actuated = len(df_actuated)
            n_total = len(df_m)
            lat_data.append({"mode": mode,
                             "T_M_ms": round(t_m, 2), "T_P_ms": round(t_p, 4),
                             "T_E_ms": round(t_e, 2), "Total_ms": round(total, 2),
                             "T_E_cond_ms": round(t_e_cond, 2), "Total_cond_ms": round(total_cond, 2),
                             "actuated_pct": round(n_actuated / n_total * 100, 1) if n_total > 0 else 0})
    tab_lat = pd.DataFrame(lat_data)

    # 7. Multi-scale breakdown (if available)
    scale_data = []
    if has_scale:
        for days in sorted(df["scale_days"].unique()):
            for mode in ["reactive", "sa_only", "sa_dt"]:
                subset = df[(df["scale_days"] == days) & (df["mode"] == mode)]
                if subset.empty:
                    continue
                success = subset["episode_success"].mean()
                ire = subset["integrated_risk"].mean()
                recovery = subset["episodes_to_recover_valid"].mean()
                scale_data.append({"scale_days": days, "mode": mode,
                                   "success_rate": round(success, 3),
                                   "ire_mean": round(ire, 3),
                                   "recovery_mean": round(recovery, 1) if not np.isnan(recovery) else "N/A"})
        pd.DataFrame(scale_data).to_csv(out_path / "multi_scale_breakdown.csv", index=False)

    # 7b. Per-scenario consolidated table
    def get_primary_scenario(s):
        match = re.match(r"(S\d+)", str(s))
        return match.group(1) if match else str(s)
    df["primary_scenario"] = df["scenario"].apply(get_primary_scenario)
    scenario_data = []
    for scenario in sorted(df["primary_scenario"].unique(), key=lambda x: (not x.startswith("S"), x)):
        for mode in ["reactive", "sa_only", "sa_dt"]:
            subset = df[(df["primary_scenario"] == scenario) & (df["mode"] == mode)]
            if subset.empty:
                continue
            uc = get_uncertainty_class(scenario) if scenario.startswith("S") else "other"
            sr = subset["episode_success"].mean()
            sr_std = subset["episode_success"].std()
            ire = subset["integrated_risk"].mean()
            ire_std = subset["integrated_risk"].std()
            ttr = subset["episodes_to_recover_valid"].mean()
            ttr_std = subset["episodes_to_recover_valid"].std()
            cost = subset["mean_cost"].mean()
            n = len(subset)
            scenario_data.append({"Scenario": scenario, "Class": uc, "Mode": mode,
                                  "SR": round(sr, 3),
                                  "SR_SD": round(sr_std, 3) if not np.isnan(sr_std) else 0,
                                  "IRE": round(ire, 3),
                                  "IRE_SD": round(ire_std, 3) if not np.isnan(ire_std) else 0,
                                  "TTR": round(ttr, 1) if not np.isnan(ttr) else -1,
                                  "TTR_SD": round(ttr_std, 1) if not np.isnan(ttr_std) else 0,
                                  "Cost": round(cost, 3), "N": n})
    pd.DataFrame(scenario_data).to_csv(out_path / "per_scenario_breakdown.csv", index=False)

    # 8. LaTeX tables
    with open(out_path / "paper_tables.tex", "w") as f:
        f.write("% Table 1: Cumulative Adaptation Results\n")
        f.write("\\begin{table*}[t]\n\\centering\n")
        f.write("\\caption{Cumulative Adaptation Results Across All Scales and Trials. ")
        f.write("Success Rate (SR), Mean Time-to-Recover (TTR$\\pm$SD), and Integrated Recovery Error (IRE$\\pm$SD). ")
        f.write("Statistical significance: $^{*}p<0.05$, $^{**}p<0.01$, $^{***}p<0.001$ (Wilcoxon signed-rank vs.\\ Reactive).}\n")
        f.write("\\label{tab:main-results}\n")
        f.write("\\begin{tabular}{llccc}\n\\toprule\n")
        f.write("\\textbf{Mode} & \\textbf{Uncertainty} & \\textbf{SR} & \\textbf{TTR (eps)} & \\textbf{IRE} \\\\\n")
        f.write("\\midrule\n")
        for _, row in agg.iterrows():
            mode_label = {"reactive": "Reactive", "sa_only": "SA-Only", "sa_dt": "SA-DT"}[row["mode"]]
            uc_label = row["uncertainty_class"].capitalize()
            sr = f"{row['success_mean']:.2f}"
            ttr = f"{row['recovery_mean']:.1f}$\\pm${row['recovery_std']:.1f}" if not np.isnan(row["recovery_mean"]) else "N/A"
            ire = f"{row['ire_mean']:.2f}$\\pm${row['ire_std']:.2f}"
            f.write(f"{mode_label} & {uc_label} & {sr} & {ttr} & {ire} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table*}\n\n")

        f.write("% Table 2: Statistical Significance Tests\n")
        f.write("\\begin{table}[t]\n\\centering\n")
        f.write("\\caption{Wilcoxon Signed-Rank Tests. $W$=test statistic, $p$=p-value, $r$=rank-biserial effect size.}\n")
        f.write("\\label{tab:stat-tests}\n")
        f.write("\\begin{tabular}{p{3.2cm}ccc}\n\\toprule\n")
        f.write("\\textbf{Comparison} & \\textbf{W} & \\textbf{p} & \\textbf{r} \\\\\n")
        f.write("\\midrule\n")
        for _, row in df_stats.iterrows():
            if row["p"] is not None:
                sig = "$^{***}$" if row["p"] < 0.001 else "$^{**}$" if row["p"] < 0.01 else "$^{*}$" if row["p"] < 0.05 else ""
                test_short = row["test"].replace("SA-DT vs ", "vs ").replace(" | ", "/")
                f.write(f"{test_short}{sig} & {row['W']:.0f} & {row['p']:.4f} & {row['effect_r']:.3f} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

        f.write("% Table 3: Latency Breakdown\n")
        f.write("\\begin{table}[t]\n\\centering\n")
        f.write("\\caption{Runtime Latency Breakdown. $T_E^{\\dagger}$ is conditioned on episodes where actuation occurred.}\n")
        f.write("\\label{tab:latency}\n")
        f.write("\\begin{tabular}{lccccc}\n\\toprule\n")
        f.write("\\textbf{Mode} & $T_M$ & $T_P$ & $T_E$ & $T_E^{\\dagger}$ & \\textbf{Act.\\%} \\\\\n")
        f.write("\\midrule\n")
        for _, row in tab_lat.iterrows():
            mode_label = {"reactive": "Reactive", "sa_only": "SA-Only", "sa_dt": "SA-DT"}[row["mode"]]
            f.write(f"{mode_label} & {row['T_M_ms']:.1f} & {row['T_P_ms']:.3f} & {row['T_E_ms']:.1f} & {row['T_E_cond_ms']:.1f} & {row['actuated_pct']:.0f}\\% \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

        if has_scale and scale_data:
            f.write("% Table 4: Multi-Scale Results\n")
            f.write("\\begin{table*}[t]\n\\centering\n")
            f.write("\\caption{Performance Across Temporal Scales.}\n")
            f.write("\\label{tab:multi-scale}\n")
            f.write("\\begin{tabular}{lcccc}\n\\toprule\n")
            f.write("\\textbf{Scale} & \\textbf{Mode} & \\textbf{SR} & \\textbf{IRE} & \\textbf{TTR} \\\\\n")
            f.write("\\midrule\n")
            for _, row in pd.DataFrame(scale_data).iterrows():
                mode_label = {"reactive": "Reactive", "sa_only": "SA-Only", "sa_dt": "SA-DT"}[row["mode"]]
                f.write(f"{row['scale_days']}d & {mode_label} & {row['success_rate']:.3f} & {row['ire_mean']:.2f} & {row['recovery_mean']} \\\\\n")
            f.write("\\bottomrule\n\\end{tabular}\n\\end{table*}\n\n")

    # 9. Figures
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="whitegrid", font_scale=1.2)
        mode_order = ["reactive", "sa_only", "sa_dt"]
        mode_labels = {"reactive": "Reactive", "sa_only": "SA-Only", "sa_dt": "SA-DT"}
        palette = {"reactive": "#e74c3c", "sa_only": "#f39c12", "sa_dt": "#2ecc71"}
        figures_dir = out_path / "figures"
        figures_dir.mkdir(exist_ok=True)

        if not agg.empty:
            uc_order = sorted(agg["uncertainty_class"].unique())
            x = np.arange(len(uc_order))
            width = 0.25

            for fig_name, metric_mean, metric_std, ylabel, title, higher_better in [
                ("fig_success_rate", "success_mean", "success_std", "Success Rate",
                 "Adaptation Success Rate by Uncertainty Class (Higher is Better)", True),
                ("fig_integrated_error", "ire_mean", "ire_std", "Integrated Recovery Error (Lower is Better) (Σr_t)",
                 "Integrated Recovery Error (Lower is Better)", False),
                ("fig_recovery_time", "recovery_mean", "recovery_std", "Episodes to Recover",
                 "Mean Time-to-Recover by Uncertainty Class (Lower is Better)", False),
            ]:
                fig, ax = plt.subplots(figsize=(8, 5))
                for i, mode in enumerate(mode_order):
                    subset = agg[agg["mode"] == mode].set_index("uncertainty_class").reindex(uc_order)
                    ax.bar(x + i * width, subset[metric_mean], width,
                           yerr=subset[metric_std], capsize=4,
                           label=mode_labels[mode], color=palette[mode], alpha=0.85)
                ax.set_xlabel("Uncertainty Class")
                ax.set_ylabel(ylabel)
                ax.set_title(title)
                ax.set_xticks(x + width)
                ax.set_xticklabels([uc.capitalize() for uc in uc_order])
                ax.legend()
                if higher_better:
                    ax.set_ylim(0, 1.0)
                plt.tight_layout()
                plt.savefig(figures_dir / f"{fig_name}.pdf", dpi=300)
                plt.savefig(figures_dir / f"{fig_name}.png", dpi=300)
                plt.close()

        if not tab_lat.empty:
            active_modes = [m for m in mode_order if not tab_lat[tab_lat["mode"] == m].empty]
            fig, ax = plt.subplots(figsize=(8, 5))
            modes_list = [mode_labels[m] for m in active_modes]
            x_pos = np.arange(len(modes_list))
            t_m_vals = [tab_lat[tab_lat["mode"] == m]["T_M_ms"].values[0] for m in active_modes]
            t_p_vals = [tab_lat[tab_lat["mode"] == m]["T_P_ms"].values[0] for m in active_modes]
            t_e_vals = [tab_lat[tab_lat["mode"] == m]["T_E_ms"].values[0] for m in active_modes]
            ax.bar(x_pos, t_m_vals, label="$T_M$ (Monitoring)", color="#3498db", alpha=0.85)
            ax.bar(x_pos, t_p_vals, bottom=t_m_vals, label="$T_P$ (Decision)", color="#9b59b6", alpha=0.85)
            bottom_2 = [a + b for a, b in zip(t_m_vals, t_p_vals)]
            ax.bar(x_pos, t_e_vals, bottom=bottom_2, label="$T_E$ (Actuation)", color="#e67e22", alpha=0.85)
            ax.set_ylabel("Latency (ms)")
            ax.set_title("System Latency Breakdown by Mode")
            ax.set_xticks(x_pos)
            ax.set_xticklabels(modes_list)
            ax.legend()
            plt.tight_layout()
            plt.savefig(figures_dir / "fig_latency_breakdown.pdf", dpi=300)
            plt.savefig(figures_dir / "fig_latency_breakdown.png", dpi=300)
            plt.close()

        if has_scale and scale_data:
            df_scale_plot = pd.DataFrame(scale_data)
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
            for mode in mode_order:
                subset = df_scale_plot[df_scale_plot["mode"] == mode]
                ax1.plot(subset["scale_days"], subset["success_rate"], "o-",
                         label=mode_labels[mode], color=palette[mode], linewidth=2, markersize=8)
                ax2.plot(subset["scale_days"], subset["ire_mean"], "o-",
                         label=mode_labels[mode], color=palette[mode], linewidth=2, markersize=8)
            ax1.set_xlabel("Temporal Scale (days)"); ax1.set_ylabel("Success Rate")
            ax1.set_title("Success Rate vs. Scale"); ax1.legend(); ax1.set_ylim(0, 1.0)
            ax2.set_xlabel("Temporal Scale (days)"); ax2.set_ylabel("Integrated Recovery Error (Lower is Better)")
            ax2.set_title("IRE vs. Scale"); ax2.legend(); ax2.set_ylim(0, None)
            plt.tight_layout()
            plt.savefig(figures_dir / "fig_multi_scale_trend.pdf", dpi=300)
            plt.savefig(figures_dir / "fig_multi_scale_trend.png", dpi=300)
            plt.close()

        print(f"Figures saved to {figures_dir}/")
    except ImportError as e:
        print(f"Notice: Plotting library not available ({e}). Skipping figure generation.")

    # 10. Text report
    report_lines.append("--- Cumulative Results ---")
    report_lines.append(agg.to_string(index=False))
    report_lines.append("")
    report_lines.append("--- Proactiveness ---")
    report_lines.append(tab_proactive.to_string(index=False))
    report_lines.append("")
    report_lines.append("--- Classification Consistency ---")
    report_lines.append(tab_acc.to_string(index=False))
    report_lines.append("")
    report_lines.append("--- Latency (Unconditional + Conditioned) ---")
    report_lines.append(tab_lat.to_string(index=False))
    report_lines.append("")
    if has_scale and scale_data:
        report_lines.append("--- Multi-Scale Breakdown ---")
        report_lines.append(pd.DataFrame(scale_data).to_string(index=False))
        report_lines.append("")

    report_text = "\n".join(report_lines)
    with open(out_path / "analysis_report.txt", "w") as f:
        f.write(report_text)

    print(report_text)
    print(f"\nAnalysis complete. Tables in {out_path}/paper_tables.tex")
    print(f"Statistical tests in {out_path}/statistical_tests.csv")
