#!/usr/bin/env python3
"""
SealSense Standalone Dataset Evaluation CLI
==========================================
Runs reproducible offline evaluation of retained bioacoustic samples against
physical ground-truth inspection records.

Usage:
  python3 backend/evaluate_dataset.py [--threshold 0.05] [--json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys

# Ensure backend directory is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.evaluation import evaluate_dataset_samples, DEFAULT_ANOMALY_THRESHOLD


def run_evaluation(db_path: str, threshold: float = DEFAULT_ANOMALY_THRESHOLD) -> dict:
    if not os.path.isfile(db_path):
        print(f"Error: Database file '{db_path}' not found.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM retained_audio_samples ORDER BY created_at DESC")
        rows = [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        print("Notice: Table 'retained_audio_samples' does not exist yet. No samples to evaluate.")
        rows = []
    finally:
        conn.close()

    report = evaluate_dataset_samples(rows, anomaly_threshold=threshold, verify_files_on_disk=True)
    return report.model_dump()


def main():
    parser = argparse.ArgumentParser(description="SealSense Bioacoustic Dataset Evaluation Utility")
    parser.add_argument("--threshold", type=float, default=DEFAULT_ANOMALY_THRESHOLD, help="Anomaly score threshold (default: 0.05)")
    parser.add_argument("--db", type=str, default=os.environ.get("SEALSENSE_DB", "sealsense.db"), help="Path to SQLite database")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of human-readable summary")
    args = parser.parse_args()

    # If relative path, check backend directory
    db_path = args.db
    if not os.path.isabs(db_path) and not os.path.exists(db_path):
        candidate = os.path.join(backend_dir, db_path)
        if os.path.exists(candidate):
            db_path = candidate

    report = run_evaluation(db_path, threshold=args.threshold)

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print("=" * 66)
    print("SEALSENSE BIOACOUSTIC DATASET EVALUATION REPORT")
    print("=" * 66)
    print(f"Timestamp:          {report['timestamp']}")
    print(f"Total Samples:      {report['total_samples']}")
    print(f"Eligible Samples:   {report['eligible_samples']}")
    print(f"Excluded Samples:   {report['excluded_samples']}")
    print("-" * 66)
    print("Exclusion Breakdown:")
    for reason, count in report["exclusion_breakdown"].items():
        print(f"  • {reason.replace('_', ' ').capitalize():<30}: {count}")
    print("-" * 66)
    print("Provenance Breakdown:")
    for src, count in report.get("provenance_breakdown", {}).items():
        print(f"  • {src.replace('_', ' ').capitalize():<30}: {count}")
    print("-" * 66)
    print("Ground-Truth Distribution:")
    for label, count in report["label_distribution"].items():
        print(f"  • {label:<30}: {count}")
    print("-" * 66)
    print(f"Anomaly Threshold:  {report['anomaly_threshold']}")

    metrics = report.get("anomaly_metrics")
    if metrics:
        print("Anomaly Detection Confusion Matrix (vs. Physical Ground-Truth):")
        print(f"  True Positives (TP):  {metrics['true_positives']}")
        print(f"  False Positives (FP): {metrics['false_positives']}")
        print(f"  True Negatives (TN):  {metrics['true_negatives']}")
        print(f"  False Negatives (FN): {metrics['false_negatives']}")
        print(f"  Precision:            {metrics['precision'] if metrics['precision'] is not None else 'N/A'}")
        print(f"  Recall (Sensitivity): {metrics['recall'] if metrics['recall'] is not None else 'N/A'}")
        print(f"  Specificity:          {metrics['specificity'] if metrics['specificity'] is not None else 'N/A'}")
        print(f"  F1 Score:             {metrics['f1_score'] if metrics['f1_score'] is not None else 'N/A'}")
    else:
        print("Classification Metrics: No eligible reviewed samples with verified ground-truth.")

    print("-" * 66)
    print(f"Vocabulary Notice:  {report['vocabulary_alignment']}")
    print(f"Limitations:        {report['limitations_notice']}")
    print("=" * 66)


if __name__ == "__main__":
    main()
