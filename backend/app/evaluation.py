"""
Reproducible Offline Dataset Evaluation Harness for SealSense Bioacoustics
========================================================================
Evaluates retained bioacoustic recordings against independently verified ground-truth
labels (e.g., physical trap inspection, grain sieve observation).

CRITICAL SCIENTIFIC, AGRONOMIC & SENSOR DOMAIN CONSTRAINTS:
1. Physical Transducer & Sensor Domain Separation:
   - Laboratory recordings from contact accelerometers, PVDF piezoelectric films,
     or ultrasonic sensors have valid biological provenance, but are SENSOR-INCOMPATIBLE
     with airborne MEMS microphones.
   - Resampling from 25 kHz/50 kHz to 16 kHz does NOT make contact vibration measurements
     equivalent to airborne headspace acoustic signals.
   - Sensor-incompatible references are STRICTLY EXCLUDED from airborne microphone performance metrics.
2. Synthetic audio signals (Poisson click bursts, simulation sweeps) are STRICTLY EXCLUDED
   from scientific evaluation metrics.
3. Unreviewed and inconclusive samples are excluded from evaluation metrics.
4. Nocturne Mini was trained on outdoor nocturnal biodiversity (InsectSet459, iNat-Sounds-2024),
   not on stored-grain pests (Sitophilus oryzae, Rhyzopertha dominica, Tribolium castaneum).
   Direct taxonomic mapping is NOT scientifically established.
5. When valid sensor-compatible evaluation data is insufficient, validation readiness is set to:
   'INSUFFICIENT VALIDATION DATA', and field-performance metrics (precision, recall, F1) are suppressed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .models import DatasetEvaluationReport, EvaluationConfusionMatrix
from .audio_storage import get_audio_file_path

log = logging.getLogger("sealsense.evaluation")

DEFAULT_ANOMALY_THRESHOLD = 0.05
TARGET_EVALUATION_DOMAIN = "airborne_microphone"


def evaluate_dataset_samples(
    samples: List[Dict[str, Any]],
    target_domain: str = TARGET_EVALUATION_DOMAIN,
    anomaly_threshold: float = DEFAULT_ANOMALY_THRESHOLD,
    verify_files_on_disk: bool = True,
) -> DatasetEvaluationReport:
    """
    Evaluates retained audio samples against verified physical observations, enforcing
    strict recording-domain separation and scientific validity criteria.

    Parameters:
    - samples: List of sample dictionaries directly from the database
    - target_domain: The sensor domain being evaluated (default: "airborne_microphone")
    - anomaly_threshold: Score threshold for anomaly detection evaluation
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

    independent_biological_labels: Dict[str, int] = {
        "TARGET_PEST_OBSERVED": 0,
        "NO_TARGET_PEST_OBSERVED": 0,
        "INCONCLUSIVE": 0,
        "UNVERIFIED": 0,
    }

    exclusion_breakdown: Dict[str, int] = {
        "synthetic_test_signal": 0,
        "synthetic_simulation": 0,
        "sensor_domain_incompatible": 0,
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

    domain_breakdown: Dict[str, int] = {
        "airborne_microphone": 0,
        "accelerometer": 0,
        "piezoelectric": 0,
        "pvdf": 0,
        "ultrasonic_transducer": 0,
        "synthetic_simulation": 0,
        "unknown": 0,
    }

    transducer_breakdown: Dict[str, int] = {}

    total_reference_recordings = 0
    total_synthetic_recordings = 0
    total_hardware_recordings = 0

    eligible_samples: List[Dict[str, Any]] = []

    for s in samples:
        src = s.get("input_source") or "user_upload"
        provenance_breakdown[src] = provenance_breakdown.get(src, 0) + 1

        if src == "public_reference":
            total_reference_recordings += 1
        elif src == "hardware_recording":
            total_hardware_recordings += 1

        is_synthetic = bool(s.get("is_synthetic")) or src == "synthetic"
        if is_synthetic:
            total_synthetic_recordings += 1

        # Recording domain tracking
        domain = s.get("recording_domain")
        if not domain or domain == "unknown":
            if is_synthetic:
                domain = "synthetic_simulation"
            elif src in ("hardware_recording", "user_upload", "live_stream", "field_recording"):
                domain = "airborne_microphone"
            elif src == "public_reference":
                # Infer from transducer_type if domain not set
                tt = (s.get("transducer_type") or "").lower()
                if "accelerometer" in tt:
                    domain = "accelerometer"
                elif "pvdf" in tt:
                    domain = "pvdf"
                elif "piezo" in tt:
                    domain = "piezoelectric"
                elif "ultrasonic" in tt:
                    domain = "ultrasonic_transducer"
                elif "microphone" in tt or "mic" in tt:
                    domain = "airborne_microphone"
                else:
                    domain = "unknown"
            else:
                domain = "unknown"

        domain_breakdown[domain] = domain_breakdown.get(domain, 0) + 1

        # Transducer type tracking
        transducer = s.get("transducer_type") or ("Synthetic Impulse Generator" if is_synthetic else "INMP441 MEMS Microphone")
        transducer_breakdown[transducer] = transducer_breakdown.get(transducer, 0) + 1

        # Biological ground truth tracking
        gt_label = s.get("ground_truth_label") or "UNREVIEWED"
        label_distribution[gt_label] = label_distribution.get(gt_label, 0) + 1

        if gt_label in independent_biological_labels:
            independent_biological_labels[gt_label] += 1
        else:
            independent_biological_labels["UNVERIFIED"] += 1

        # ─── ELIGIBILITY AUDIT ──────────────────────────────────────────
        # Rule 1: Exclude synthetic signals
        if is_synthetic or domain == "synthetic_simulation":
            exclusion_breakdown["synthetic_simulation"] += 1
            exclusion_breakdown["synthetic_test_signal"] += 1
            continue

        # Rule 2: Verify audio file on disk
        if verify_files_on_disk:
            stored_fn = s.get("stored_filename")
            if not stored_fn or not get_audio_file_path(stored_fn):
                exclusion_breakdown["missing_audio_file"] += 1
                continue

        # Rule 3: Exclude sensor-incompatible public references from field microphone evaluation
        if domain != target_domain:
            exclusion_breakdown["sensor_domain_incompatible"] += 1
            continue

        # Rule 4: Exclude unreviewed
        if gt_label == "UNREVIEWED":
            exclusion_breakdown["unreviewed_sample"] += 1
            continue

        # Rule 5: Exclude inconclusive
        if gt_label == "INCONCLUSIVE":
            exclusion_breakdown["inconclusive_observation"] += 1
            continue

        # Retain only sensor-compatible samples with definitive biological labels
        if gt_label in ("TARGET_PEST_OBSERVED", "NO_TARGET_PEST_OBSERVED"):
            eligible_samples.append(s)

    eligible_count = len(eligible_samples)
    excluded_count = total_samples - eligible_count

    # Check validation readiness
    # Ground-truth evaluation requires both positive and negative sensor-compatible samples
    pos_count = sum(1 for s in eligible_samples if s.get("ground_truth_label") == "TARGET_PEST_OBSERVED")
    neg_count = sum(1 for s in eligible_samples if s.get("ground_truth_label") == "NO_TARGET_PEST_OBSERVED")

    is_evaluation_valid = (eligible_count > 0 and pos_count > 0 and neg_count > 0)
    validation_readiness = "VALID_EVALUATION_SET" if is_evaluation_valid else "INSUFFICIENT VALIDATION DATA"

    # Evaluate confusion matrix ONLY if valid evaluation set exists
    confusion: Optional[EvaluationConfusionMatrix] = None
    grouped_by_zone: Dict[str, Dict[str, Any]] = {}

    if is_evaluation_valid:
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

        confusion = EvaluationConfusionMatrix(
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
        )

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        specificity = (tn / (tn + fp)) if (tn + fp) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        confusion.precision = round(precision, 4)
        confusion.recall = round(recall, 4)
        confusion.specificity = round(specificity, 4)
        confusion.f1_score = round(f1, 4)
    else:
        # Strict scientific safeguard: do NOT report precision, recall, or F1
        confusion = None

    vocabulary_alignment = (
        "Model vocabulary is outdoor nocturnal biodiversity (InsectSet459/iNat-Sounds-2024; 2,182 classes); "
        "direct taxonomic classification of grain-pest species (Sitophilus oryzae, Rhyzopertha dominica) "
        "is not scientifically established. Nocturne activations must NOT be used to claim stored-grain pest accuracy."
    )

    limitations_notice = (
        "Evaluation strictly separates biological ground truth from model evaluation eligibility. "
        "All synthetic audio is excluded from scientific metrics. "
        "Laboratory reference recordings (e.g. USDA Bug Bytes) originate from contact accelerometers, PVDF films, "
        "or ultrasonic transducers; they demonstrate authentic pest bioacoustics but are sensor-incompatible with "
        f"airborne {target_domain} deployments and are excluded from field validation. "
        "When valid sensor-compatible evaluation data is insufficient, field-performance metrics are suppressed."
    )

    return DatasetEvaluationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        validation_readiness=validation_readiness,
        target_evaluation_domain=target_domain,
        total_samples=total_samples,
        total_reference_recordings=total_reference_recordings,
        total_synthetic_recordings=total_synthetic_recordings,
        total_hardware_recordings=total_hardware_recordings,
        eligible_samples=eligible_count,
        excluded_samples=excluded_count,
        eligible_recording_domains=[target_domain],
        domain_breakdown=domain_breakdown,
        transducer_breakdown=transducer_breakdown,
        exclusion_breakdown=exclusion_breakdown,
        label_distribution=label_distribution,
        independent_biological_labels=independent_biological_labels,
        vocabulary_alignment=vocabulary_alignment,
        anomaly_threshold=anomaly_threshold,
        anomaly_metrics=confusion,
        grouped_by_zone=grouped_by_zone,
        provenance_breakdown=provenance_breakdown,
        limitations_notice=limitations_notice,
    )
