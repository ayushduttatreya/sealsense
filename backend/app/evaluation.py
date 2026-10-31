"""
Reproducible Offline Dataset Evaluation Harness for SealSense Bioacoustics
========================================================================
Evaluates retained bioacoustic recordings against independently verified ground-truth
labels (e.g., physical trap inspection, grain sieve observation).

CRITICAL SCIENTIFIC & AGRONOMIC CONSTRAINTS:
1. Synthetic audio signals (browser sweeps, noise chirps) are strictly excluded from evaluation.
2. Unreviewed and inconclusive samples are excluded from evaluation metrics.
3. Nocturne Mini was trained on outdoor nocturnal biodiversity (InsectSet459, iNat-Sounds-2024),
   not on stored-grain pests (Sitophilus oryzae, Rhyzopertha dominica, Tribolium castaneum).
4. Direct taxonomic mapping between outdoor species activations and grain pests is NOT scientifically
   established. Metric evaluation is therefore strictly restricted to evaluating model anomaly score
   thresholding against physical trap ground-truth.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .models import DatasetEvaluationReport, EvaluationConfusionMatrix
from .audio_storage import get_audio_file_path

log = logging.getLogger("sealsense.evaluation")

DEFAULT_ANOMALY_THRESHOLD = 0.05


def evaluate_dataset_samples(
    samples: List[Dict[str, Any]],
    anomaly_threshold: float = DEFAULT_ANOMALY_THRESHOLD,
    verify_files_on_disk: bool = True,
) -> DatasetEvaluationReport:
    """
    Evaluates a collection of retained audio samples against verified physical observations.

    Parameters:
    - samples: List of sample dictionaries directly from the database
    - anomaly_threshold: Score threshold above which audio is classified as an acoustic anomaly
    - verify_files_on_disk: Whether to verify that the audio file is physically present in storage
    """
    total_samples = len(samples)
    label_distribution: Dict[str, int] = {
        "UNREVIEWED": 0,
        "REVIEWED": 0,
        "TARGET_PEST_OBSERVED": 0,
        "NO_TARGET_PEST_OBSERVED": 0,
        "INCONCLUSIVE": 0,
    }

    exclusion_breakdown: Dict[str, int] = {
        "synthetic_test_signal": 0,
        "unreviewed_sample": 0,
        "inconclusive_observation": 0,
        "missing_audio_file": 0,
    }

    provenance_breakdown: Dict[str, int] = {
        "public_reference": 0,
        "user_upload": 0,
        "hardware_recording": 0,
        "synthetic": 0,
    }

    eligible_samples: List[Dict[str, Any]] = []

    for s in samples:
        src = s.get("input_source") or "user_upload"
        provenance_breakdown[src] = provenance_breakdown.get(src, 0) + 1

        gt_label = s.get("ground_truth_label") or "UNREVIEWED"
        label_distribution[gt_label] = label_distribution.get(gt_label, 0) + 1

        is_synthetic = bool(s.get("is_synthetic")) or src == "synthetic"
        if is_synthetic:
            exclusion_breakdown["synthetic_test_signal"] += 1
            continue

        if verify_files_on_disk:
            stored_fn = s.get("stored_filename")
            if not stored_fn or not get_audio_file_path(stored_fn):
                exclusion_breakdown["missing_audio_file"] += 1
                continue

        if gt_label == "UNREVIEWED":
            exclusion_breakdown["unreviewed_sample"] += 1
            continue

        if gt_label == "INCONCLUSIVE":
            exclusion_breakdown["inconclusive_observation"] += 1
            continue

        if gt_label in ("TARGET_PEST_OBSERVED", "NO_TARGET_PEST_OBSERVED"):
            eligible_samples.append(s)

    eligible_count = len(eligible_samples)
    excluded_count = total_samples - eligible_count

    # Evaluate Anomaly Score Thresholding against Ground-Truth Physical Traps
    confusion = EvaluationConfusionMatrix()
    grouped_by_zone: Dict[str, Dict[str, Any]] = {}

    if eligible_count > 0:
        tp, fp, tn, fn = 0, 0, 0, 0

        for s in eligible_samples:
            score = float(s.get("score") or 0.0)
            gt_label = s.get("ground_truth_label")
            zone = s.get("zone_id") or "unknown"

            if zone not in grouped_by_zone:
                grouped_by_zone[zone] = {"total": 0, "positive_label": 0, "negative_label": 0, "anomaly_flagged": 0}
            grouped_by_zone[zone]["total"] += 1

            is_pest_observed = (gt_label == "TARGET_PEST_OBSERVED")
            is_anomaly_predicted = (score >= anomaly_threshold)

            if is_pest_observed:
                grouped_by_zone[zone]["positive_label"] += 1
            else:
                grouped_by_zone[zone]["negative_label"] += 1

            if is_anomaly_predicted:
                grouped_by_zone[zone]["anomaly_flagged"] += 1

            if is_pest_observed and is_anomaly_predicted:
                tp += 1
            elif not is_pest_observed and is_anomaly_predicted:
                fp += 1
            elif not is_pest_observed and not is_anomaly_predicted:
                tn += 1
            elif is_pest_observed and not is_anomaly_predicted:
                fn += 1

        confusion.true_positives = tp
        confusion.false_positives = fp
        confusion.true_negatives = tn
        confusion.false_negatives = fn

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        specificity = (tn / (tn + fp)) if (tn + fp) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        confusion.precision = round(precision, 4)
        confusion.recall = round(recall, 4)
        confusion.specificity = round(specificity, 4)
        confusion.f1_score = round(f1, 4)
    else:
        confusion = None

    vocabulary_alignment = (
        "Model vocabulary is outdoor biodiversity (InsectSet459/iNat-Sounds-2024; 2,182 classes); "
        "direct taxonomic classification of grain-pest species (Sitophilus oryzae, Rhyzopertha dominica) "
        "is not scientifically established. The anomaly metrics evaluate whether acoustic energy / prediction "
        f"scores above threshold {anomaly_threshold} correlate with physical kernel trap findings."
    )

    limitations_notice = (
        "Evaluation strictly reflects current labeled data. "
        "Synthetic signals, unreviewed audio, and inconclusive samples are excluded. "
        "Public reference recordings (e.g. USDA Bug Bytes) originate from laboratory acoustic isolation chambers "
        "using contact accelerometers or PVDF film sensors; they demonstrate algorithmic behavior but do not validate "
        "field microphone performance or live hardware accuracy. Do not interpret anomaly score correlation as automated grain pest classification."
    )

    return DatasetEvaluationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_samples=total_samples,
        eligible_samples=eligible_count,
        excluded_samples=excluded_count,
        exclusion_breakdown=exclusion_breakdown,
        label_distribution=label_distribution,
        vocabulary_alignment=vocabulary_alignment,
        anomaly_threshold=anomaly_threshold,
        anomaly_metrics=confusion,
        grouped_by_zone=grouped_by_zone,
        provenance_breakdown=provenance_breakdown,
        limitations_notice=limitations_notice,
    )
