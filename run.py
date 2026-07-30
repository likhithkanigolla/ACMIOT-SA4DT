#!/usr/bin/env python3
"""
run.py — Single Entry Point for the SA-DT Evaluation Pipeline
==============================================================

Paper: "Digital Twins for Uncertainty Mitigation in Self-Adaptive Smart City IoT Systems"
Venue: IoT '26 — 16th International Conference on the Internet of Things

This script wires together the complete MAPE-K + Digital Twin pipeline in the
exact component order described in the paper (Section 5, Figure 1):

    Monitor → Analyse → Plan → [DT Simulation Gate] → Decision Engine → Execute → Shared Knowledge

A paper reviewer can run this script to:
  - Exercise the full pipeline for any mode / scale / scenario combination
  - Print a step-by-step component trace matched to Figure 1
  - Reproduce the exact experiment configurations used for Tables 2-4 and Figures 2-5

Usage examples:
  python run.py --mode sa_dt --scale 1 --seed 42 --scenario all --trace
  python run.py --mode reactive --scale 7 --seed 0
  python run.py --reproduce-table 2
  python run.py --reproduce-figure 2

Run `python run.py --help` for full documentation.
"""

import argparse
import sys
import textwrap
from pathlib import Path

# Make src/ importable from this root script
sys.path.insert(0, str(Path(__file__).parent))

from src.managing_system.shared_knowledge.knowledge_store import Config, KnowledgeStore
from src.common.modes.reactive_baseline import ReactiveBaseline
from src.common.modes.sa_only import SAOnly
from src.common.modes.sa_dt import SADT
from src.common.data_generator import generate_dataset
from src.common.trace_runner import run_all_modes
from src.common.analysis import run_analysis


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"
RESULTS_DIR = ROOT / "results"
UNCERTAINTY_PROFILE = CONFIG_DIR / "uncertainty_profile.json"

# Modes that can be selected via --mode
MODE_MAP = {
    "reactive": "ReactiveBaseline  — static threshold rules; no MAPE-K, no DT (paper §4, baseline 1)",
    "sa_only":  "SAOnly            — full MAPE-K, no DT simulation (paper §4, baseline 2)",
    "sa_dt":    "SADT              — proposed: MAPE-K + DT Simulation Gate + Utility Evaluator (paper §4)",
}

# Reproduce-table / reproduce-figure configurations
TABLE_CONFIGS = {
    2: {"scales": [1, 7, 15, 30], "trials": 5,
        "description": "Table 2: Cumulative Adaptation Results (SR, TTR, IRE) across all scales"},
    3: {"scales": [1, 7, 15, 30], "trials": 5,
        "description": "Table 3: Runtime Latency Breakdown (T_M, T_P, T_E, T_E-cond)"},
    4: {"scales": [1, 7, 15, 30], "trials": 5,
        "description": "Table 4: Multi-Scale Performance (SR, IRE, TTR per scale)"},
}
FIGURE_CONFIGS = {
    2: {"description": "Figure 2: Success Rate by Uncertainty Class"},
    3: {"description": "Figure 3: Integrated Recovery Error (Lower is Better) by Uncertainty Class"},
    4: {"description": "Figure 4: Runtime Latency Stacked Bar"},
    5: {"description": "Figure 5: Multi-Scale Success Rate and IRE Trend"},
}


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            SA-DT Evaluation Pipeline — Single Entry Point
            ===============================================
            Paper: "Digital Twins for Uncertainty Mitigation in Self-Adaptive
                    Smart City IoT Systems" (IoT '26)

            Component pipeline (Figure 1):
              Monitor → Analyse → Plan → [DT Gate if mode=sa_dt]
                → Decision Engine → Execute → Shared Knowledge

            Quick-start:
              python run.py --mode sa_dt --scale 1 --seed 42 --trace
              python run.py --reproduce-table 2
        """),
    )

    # -- Core options --
    parser.add_argument(
        "--mode",
        choices=["reactive", "sa_only", "sa_dt", "all"],
        default="all",
        help=textwrap.dedent("""\
            Execution mode (paper §4):
              reactive  — Static threshold rules; no MAPE-K, no DT
              sa_only   — Full MAPE-K loop; no DT simulation gate
              sa_dt     — Proposed: MAPE-K + DT simulation gate + utility evaluator
              all       — Run all three modes sequentially (default)
            Default: all"""),
    )
    parser.add_argument(
        "--scale",
        type=int,
        choices=[1, 7, 15, 30],
        default=1,
        help="Temporal scale in days (paper §5: 1/7/15/30-day trials). Default: 1",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for data generation and reproducibility. Default: 42",
    )
    parser.add_argument(
        "--scenario",
        default="all",
        help=textwrap.dedent("""\
            Fault scenario filter (paper Table 1):
              S1  — Sensor Drift            (epistemic)
              S2  — Model Error             (epistemic)
              S3  — Actuation Deviation     (epistemic)
              S4  — Stuck Sensor            (epistemic)
              S5  — Behavioral Drift        (epistemic)
              S6  — Actuator Failure        (epistemic)
              S7  — Measurement Noise       (aleatoric)
              S8  — Packet Loss             (aleatoric)
              S9  — Network Instability     (aleatoric)
              S10 — Reconnection Events     (aleatoric)
              S11 — Environmental Variab.   (aleatoric)
              all — Run all scenarios (default)
            Default: all"""),
    )
    parser.add_argument(
        "--output-dir",
        default=str(RESULTS_DIR),
        help="Output directory for raw_episodes, trial_summary, and analysis CSVs.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print a step-by-step MAPE-K component trace per episode (matches Figure 1).",
    )
    parser.add_argument(
        "--no-data-gen",
        action="store_true",
        help="Skip data generation (use existing synthetic_telemetry.csv in --output-dir).",
    )

    # -- Reproduce paper results --
    parser.add_argument(
        "--reproduce-table",
        type=int,
        choices=[2, 3, 4],
        metavar="{2,3,4}",
        help=textwrap.dedent("""\
            Reproduce one of the paper's tables.
              2 → Table 2: Cumulative SR/TTR/IRE/Cost results (§5, all scales × 5 seeds)
              3 → Table 3: Latency breakdown T_M/T_P/T_E/T_E-cond
              4 → Table 4: Multi-scale performance trend"""),
    )
    parser.add_argument(
        "--reproduce-figure",
        type=int,
        choices=[2, 3, 4, 5],
        metavar="{2,3,4,5}",
        help=textwrap.dedent("""\
            Reproduce one of the paper's figures.
              2 → Figure 2: Success rate by uncertainty class
              3 → Figure 3: Integrated Recovery Error (Lower is Better) by uncertainty class
              4 → Figure 4: Latency stacked bar
              5 → Figure 5: Multi-scale SR and IRE trend"""),
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Skip experiment run; run analysis only on existing results in --output-dir.",
    )

    return parser


# ---------------------------------------------------------------------------
# Mode factory
# ---------------------------------------------------------------------------

def make_mode(mode_name: str, knowledge_store: KnowledgeStore):
    """Instantiate the AdaptationMode strategy for the given mode name."""
    if mode_name == "reactive":
        return ReactiveBaseline()
    elif mode_name == "sa_only":
        return SAOnly()
    elif mode_name == "sa_dt":
        return SADT(knowledge_store)
    else:
        raise ValueError(f"Unknown mode: {mode_name}")


# ---------------------------------------------------------------------------
# Single-run pipeline
# ---------------------------------------------------------------------------

def run_single(args) -> None:
    """Run one (mode, scale, seed) experiment."""
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = Config()
    ks = KnowledgeStore(config)

    csv_path = out_dir / "synthetic_telemetry.csv"

    # -- Data generation --
    if not args.no_data_gen:
        print(f"\n[DataGenerator] Generating {args.scale}-day synthetic telemetry (seed={args.seed})...")
        print(f"  Profile:  {UNCERTAINTY_PROFILE}")
        print(f"  Scenarios: all S1-S11 (paper Table 1)")
        df = generate_dataset(
            days=args.scale,
            seed=args.seed,
            profile_path=UNCERTAINTY_PROFILE,
            out_file=csv_path,
        )
        print(f"  ✓ {len(df)} rows written to {csv_path}")
    else:
        if not csv_path.exists():
            print(f"Error: --no-data-gen specified but {csv_path} does not exist.")
            sys.exit(1)
        print(f"[DataGenerator] Skipping — using existing {csv_path}")

    if args.analyze_only:
        print("\n[Analysis] Running analysis on existing results...")
        run_analysis(str(out_dir))
        return

    # -- Mode selection --
    print(f"\n[Pipeline ] Mode: {args.mode}  |  Scale: {args.scale} days  |  Seed: {args.seed}")
    if args.trace:
        print("[Pipeline ] --trace enabled: printing per-episode component output\n")

    # -- Run MAPE-K trace --
    print(f"\n[Pipeline ] MAPE-K Component Order (Figure 1):")
    print(f"  Monitor → Analyse → Plan → " +
          ("[DT Simulation Gate] → " if args.mode in ("sa_dt", "all") else "[No DT Gate] → ") +
          "Decision Engine → Execute → Shared Knowledge\n")

    if args.mode == "all":
        modes_to_run = [
            ReactiveBaseline(),
            SAOnly(),
            SADT(KnowledgeStore(config)),
        ]
    else:
        modes_to_run = [make_mode(args.mode, KnowledgeStore(config))]

    run_all_modes(
        csv_path=str(csv_path),
        output_dir=str(out_dir),
        config=config,
        modes=modes_to_run,
        trace=args.trace,
    )

    print(f"\n[Analysis ] Running post-run analysis...")
    run_analysis(str(out_dir))
    print(f"\n✓ Run complete. Results in: {out_dir}/")


# ---------------------------------------------------------------------------
# Reproduce-table / reproduce-figure (full multi-scale experiment)
# ---------------------------------------------------------------------------

def run_reproduce(table_num=None, figure_num=None, args=None) -> None:
    """
    Reproduce a specific table or figure from the paper.
    Runs all 4 scales × 5 seeds × 3 modes (same as the full paper experiment).
    """
    out_dir = Path(args.output_dir if args else RESULTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    target = f"Table {table_num}" if table_num else f"Figure {figure_num}"
    desc_map = {**{f"t{k}": v["description"] for k, v in TABLE_CONFIGS.items()},
                **{f"f{k}": v["description"] for k, v in FIGURE_CONFIGS.items()}}
    key = f"t{table_num}" if table_num else f"f{figure_num}"
    print(f"\n{'='*65}")
    print(f"REPRODUCING: {desc_map.get(key, target)}")
    print(f"{'='*65}")
    print(f"Experiment: 4 scales × 5 seeds × 3 modes = 60 total runs")
    print(f"Output dir: {out_dir}\n")

    import csv as _csv
    import json as _json

    all_summaries = []
    all_raws = []
    trial_id_offset = 0

    scales = [1, 7, 15, 30]
    n_trials = 5
    config = Config()

    for days in scales:
        for trial in range(n_trials):
            seed = trial  # deterministic per trial
            print(f"\n  Scale={days}d | Trial={trial+1}/{n_trials} | seed={seed}")

            trial_dir = out_dir / f"scale_{days}d_trial_{trial+1}"
            trial_dir.mkdir(exist_ok=True)
            csv_path = trial_dir / "synthetic_telemetry.csv"

            # Generate data
            generate_dataset(
                days=days, seed=seed,
                profile_path=UNCERTAINTY_PROFILE,
                out_file=csv_path,
            )

            # Run all three modes
            modes = [
                ReactiveBaseline(),
                SAOnly(),
                SADT(KnowledgeStore(config)),
            ]
            run_all_modes(
                csv_path=str(csv_path),
                output_dir=str(trial_dir),
                config=config,
                modes=modes,
                trace=False,
            )

            # Aggregate trial summary
            sum_file = trial_dir / "trial_summary.csv"
            raw_file = trial_dir / "raw_episodes.jsonl"
            if sum_file.exists():
                import pandas as pd
                df_sum = pd.read_csv(sum_file)
                df_sum["scale_days"] = days
                df_sum["global_trial_id"] = trial_id_offset + df_sum["trial_seed"]
                all_summaries.append(df_sum)
            if raw_file.exists():
                with open(raw_file) as f:
                    all_raws.extend(f.readlines())

            trial_id_offset += 1000

    # Combine and re-analyze
    import pandas as pd
    final_summary = pd.concat(all_summaries, ignore_index=True)
    final_summary.to_csv(out_dir / "trial_summary.csv", index=False)
    with open(out_dir / "raw_episodes.jsonl", "w") as f:
        f.writelines(all_raws)

    print(f"\n[Analysis ] Running final analysis across all {len(scales) * n_trials} runs...")
    run_analysis(str(out_dir))

    print(f"\n✓ Reproduction complete.")
    if table_num:
        print(f"  → LaTeX table in: {out_dir}/paper_tables.tex")
    if figure_num:
        print(f"  → Figures in: {out_dir}/figures/")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.reproduce_table or args.reproduce_figure:
        run_reproduce(
            table_num=args.reproduce_table,
            figure_num=args.reproduce_figure,
            args=args,
        )
    else:
        run_single(args)


if __name__ == "__main__":
    main()
