"""
run_benchmark.py - CLI Entrypoint for UIDAI Synthetic Attack Benchmark & Ablation Study.

Usage:
    python run_benchmark.py --samples 5
    python run_benchmark.py --samples 2 --ablation
    python run_benchmark.py --vectors A1,A4,A6,A14 --samples 3
"""

import sys
import argparse
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

from modules.synthetic.benchmark_runner import BenchmarkRunner


def main():
    parser = argparse.ArgumentParser(description="UIDAI Synthetic Attack Benchmark & Ablation Runner")
    parser.add_argument("--samples", type=int, default=3, help="Number of samples to evaluate per attack vector")
    parser.add_argument("--ablation", action="store_true", help="Execute defense layer ablation study")
    parser.add_argument("--vectors", type=str, default=None, help="Comma-separated vector IDs (e.g. A1,A4,A14)")
    parser.add_argument("--report-md", type=str, default="data/reports/benchmark_report.md", help="Markdown report output path")
    parser.add_argument("--report-json", type=str, default="data/reports/benchmark_results.json", help="JSON report output path")
    args = parser.parse_args()

    vector_list = [v.strip().upper() for v in args.vectors.split(",")] if args.vectors else None

    runner = BenchmarkRunner()
    report = runner.run_benchmark(
        samples_per_vector=args.samples,
        vectors=vector_list,
        verbose=True
    )

    if args.ablation:
        ablation = runner.run_ablation_study(verbose=True)
        report.ablation_results = ablation

    # Export reports
    md_content = runner.export_report_markdown(report, output_path=args.report_md)
    runner.export_report_json(report, output_path=args.report_json)

    print("\n" + "=" * 60)
    print("  BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total Evaluated:          {report.total_samples}")
    print(f"Overall Accuracy:         {report.overall_accuracy:.1f}%")
    print(f"Fraud Detection Rate:     {report.fraud_detection_rate:.1f}%")
    print(f"Genuine Acceptance Rate:  {report.genuine_acceptance_rate:.1f}%")
    print(f"False Reject Rate:        {report.false_reject_rate:.1f}%")
    print(f"P50 / P95 Latency:        {report.p50_latency_ms:.1f}ms / {report.p95_latency_ms:.1f}ms")
    print(f"Markdown Report Saved:    {args.report_md}")
    print(f"JSON Results Saved:       {args.report_json}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
