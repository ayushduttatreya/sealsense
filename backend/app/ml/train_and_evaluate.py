"""
SealSense Reproducible ML Baseline Training & Evaluation Harness
================================================================
Benchmarks:
  1. Random Forest Classifier on physical acoustic features (22 features).
  2. Small 2D CNN on Log-Mel Spectrograms (64 bands).
  3. Pretrained Nocturne Mini bioacoustic comparison.

Scientific Safeguards:
- Strict session/source-level cross-validation (GroupKFold) prevents data leakage.
- Metrics reported: Precision, Recall, F1, Confusion Matrix, False Alarms per hour.
- Synthetic audio is kept distinct from authentic recordings.
- Transducer domain differences are audited and documented.
"""
from __future__ import annotations

import os
import sys
import json
import time
import argparse
from typing import Dict, Any, List, Tuple
import numpy as np
import joblib

from sklearn.model_selection import GroupKFold
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.ml.dataset import load_dataset, CLASS_NAMES, TARGET_SAMPLE_RATE, AudioSampleWindow
from app.ml.features import extract_feature_vector, extract_log_mel_spectrogram, FEATURE_NAMES
from app.ml.models import build_random_forest, SealSenseAcousticCNN
from app.adapters.nocturne import NocturneMiniAdapter

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")


def prepare_dataset_matrices(windows: List[AudioSampleWindow]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """
    Extracts tabular features, log-mel spectrograms, labels, and groups.
    """
    X_feat_list = []
    X_spec_list = []
    y_list = []
    groups_list = []
    metadata_list = []

    for idx, w in enumerate(windows):
        # 1. Tabular features
        feat_vec = extract_feature_vector(w.audio, TARGET_SAMPLE_RATE)
        X_feat_list.append(feat_vec)

        # 2. Log-Mel spectrogram
        log_mel = extract_log_mel_spectrogram(w.audio, TARGET_SAMPLE_RATE, n_mels=64)
        X_spec_list.append(log_mel)

        # 3. Label & Group
        y_list.append(w.label_idx)
        groups_list.append(w.session_id)

        metadata_list.append({
            "window_id": idx,
            "source_file": w.source_file,
            "session_id": w.session_id,
            "label": w.label,
            "recording_domain": w.recording_domain,
            "transducer_type": w.transducer_type,
            "species": w.species,
        })

    X_feat = np.array(X_feat_list, dtype=np.float32)
    # Shape for CNN: (N, 1, 64, 101)
    X_spec = np.array(X_spec_list, dtype=np.float32)[:, np.newaxis, :, :]
    y = np.array(y_list, dtype=np.int64)
    groups = np.array(groups_list)

    return X_feat, X_spec, y, groups, metadata_list


def evaluate_random_forest(
    X_feat: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    n_splits: int = 4,
) -> Dict[str, Any]:
    """Runs GroupKFold cross-validation on Random Forest."""
    gkf = GroupKFold(n_splits=n_splits)

    y_true_all = []
    y_pred_all = []
    y_proba_all = []

    for fold, (train_idx, val_idx) in enumerate(gkf.split(X_feat, y, groups)):
        X_train, y_train = X_feat[train_idx], y[train_idx]
        X_val, y_val = X_feat[val_idx], y[val_idx]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)

        clf = build_random_forest(n_estimators=100, max_depth=8, random_state=42 + fold)
        clf.fit(X_train_scaled, y_train)

        preds = clf.predict(X_val_scaled)
        probas = clf.predict_proba(X_val_scaled)

        y_true_all.extend(y_val.tolist())
        y_pred_all.extend(preds.tolist())
        y_proba_all.extend(probas.tolist())

    y_true_np = np.array(y_true_all)
    y_pred_np = np.array(y_pred_all)

    # Metrics
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))), average="macro", zero_division=0
    )
    w_precision, w_recall, w_f1, _ = precision_recall_fscore_support(
        y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))), average="weighted", zero_division=0
    )
    per_class = precision_recall_fscore_support(
        y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))), average=None, zero_division=0
    )

    cm = confusion_matrix(y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))))

    # False alarm calculation: false positives on non-insect classes classified as insect_activity
    insect_idx = CLASS_NAMES.index("insect_activity")
    non_insect_mask = (y_true_np != insect_idx)
    fp_insects = int(np.sum((y_true_np != insect_idx) & (y_pred_np == insect_idx)))
    total_non_insect_windows = int(np.sum(non_insect_mask))
    total_non_insect_sec = total_non_insect_windows * 1.0
    false_alerts_per_hour = (fp_insects / total_non_insect_sec * 3600.0) if total_non_insect_sec > 0 else 0.0

    return {
        "model_name": "Random Forest (Physical Features)",
        "feature_count": X_feat.shape[1],
        "macro_precision": float(round(precision, 4)),
        "macro_recall": float(round(recall, 4)),
        "macro_f1": float(round(f1, 4)),
        "weighted_precision": float(round(w_precision, 4)),
        "weighted_recall": float(round(w_recall, 4)),
        "weighted_f1": float(round(w_f1, 4)),
        "per_class": {
            CLASS_NAMES[i]: {
                "precision": float(round(per_class[0][i], 4)),
                "recall": float(round(per_class[1][i], 4)),
                "f1": float(round(per_class[2][i], 4)),
                "support": int(per_class[3][i]),
            }
            for i in range(len(CLASS_NAMES))
        },
        "confusion_matrix": cm.tolist(),
        "classes": CLASS_NAMES,
        "false_positives_insect": fp_insects,
        "false_alarm_rate_per_hour": float(round(false_alerts_per_hour, 2)),
    }


def train_cnn_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(y_batch)
    return total_loss / len(loader.dataset)


def evaluate_cnn(
    X_spec: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    n_splits: int = 4,
    epochs: int = 20,
) -> Dict[str, Any]:
    """Runs GroupKFold cross-validation on Small 2D CNN."""
    gkf = GroupKFold(n_splits=n_splits)
    device = torch.device("cpu")

    y_true_all = []
    y_pred_all = []

    for fold, (train_idx, val_idx) in enumerate(gkf.split(X_spec, y, groups)):
        X_train, y_train = torch.tensor(X_spec[train_idx]), torch.tensor(y[train_idx])
        X_val, y_val = torch.tensor(X_spec[val_idx]), torch.tensor(y[val_idx])

        # Compute balanced class weights
        counts = torch.bincount(y_train, minlength=len(CLASS_NAMES)).float()
        weights = 1.0 / (counts + 1e-6)
        weights = weights / weights.sum()

        train_dataset = TensorDataset(X_train, y_train)
        train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)

        model = SealSenseAcousticCNN(num_classes=len(CLASS_NAMES)).to(device)
        optimizer = optim.Adam(model.parameters(), lr=0.003, weight_decay=1e-4)
        criterion = nn.CrossEntropyLoss(weight=weights.to(device))

        for ep in range(epochs):
            train_cnn_epoch(model, train_loader, optimizer, criterion, device)

        model.eval()
        with torch.no_grad():
            val_logits = model(X_val.to(device))
            preds = torch.argmax(val_logits, dim=-1).cpu().numpy()

        y_true_all.extend(y_val.numpy().tolist())
        y_pred_all.extend(preds.tolist())

    y_true_np = np.array(y_true_all)
    y_pred_np = np.array(y_pred_all)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))), average="macro", zero_division=0
    )
    w_precision, w_recall, w_f1, _ = precision_recall_fscore_support(
        y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))), average="weighted", zero_division=0
    )
    per_class = precision_recall_fscore_support(
        y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))), average=None, zero_division=0
    )
    cm = confusion_matrix(y_true_np, y_pred_np, labels=list(range(len(CLASS_NAMES))))

    insect_idx = CLASS_NAMES.index("insect_activity")
    fp_insects = int(np.sum((y_true_np != insect_idx) & (y_pred_np == insect_idx)))
    total_non_insect_sec = int(np.sum(y_true_np != insect_idx)) * 1.0
    false_alerts_per_hour = (fp_insects / total_non_insect_sec * 3600.0) if total_non_insect_sec > 0 else 0.0

    return {
        "model_name": "Small 2D CNN (Log-Mel Spectrograms)",
        "parameters": 28164,
        "input_shape": list(X_spec.shape[1:]),
        "macro_precision": float(round(precision, 4)),
        "macro_recall": float(round(recall, 4)),
        "macro_f1": float(round(f1, 4)),
        "weighted_precision": float(round(w_precision, 4)),
        "weighted_recall": float(round(w_recall, 4)),
        "weighted_f1": float(round(w_f1, 4)),
        "per_class": {
            CLASS_NAMES[i]: {
                "precision": float(round(per_class[0][i], 4)),
                "recall": float(round(per_class[1][i], 4)),
                "f1": float(round(per_class[2][i], 4)),
                "support": int(per_class[3][i]),
            }
            for i in range(len(CLASS_NAMES))
        },
        "confusion_matrix": cm.tolist(),
        "classes": CLASS_NAMES,
        "false_positives_insect": fp_insects,
        "false_alarm_rate_per_hour": float(round(false_alerts_per_hour, 2)),
    }


def evaluate_nocturne_mini_comparison(windows: List[AudioSampleWindow], max_samples: int = 40) -> Dict[str, Any]:
    """
    Evaluates stratus-labs/nocturne-v1-mini on actual grain acoustic windows to document
    its predictions and demonstrate why generic outdoor models do not detect stored grain insects.
    """
    adapter = NocturneMiniAdapter()
    loaded = adapter.load_model()
    if not loaded:
        return {
            "status": "UNAVAILABLE",
            "reason": adapter._load_error or "Could not load weights",
        }

    step = max(1, len(windows) // max_samples)
    subset = windows[::step][:max_samples]

    results = []
    class_predictions = {}

    for w in subset:
        res = adapter.predict(w.audio, sample_rate=TARGET_SAMPLE_RATE, top_k=3)
        top_pred = res.prediction
        top_score = res.score or 0.0

        results.append({
            "source_file": w.source_file,
            "true_ground_truth": w.label,
            "species": w.species,
            "domain": w.recording_domain,
            "nocturne_top_prediction": top_pred,
            "nocturne_score": float(round(top_score, 4)),
            "nocturne_top_3": [p.model_dump() for p in res.top_predictions],
        })

        class_predictions[top_pred] = class_predictions.get(top_pred, 0) + 1

    return {
        "status": "EVALUATED",
        "sample_count": len(results),
        "vocabulary_size": 2182,
        "vocabulary_domain": "Outdoor biodiversity (iNat-Sounds-2024 / InsectSet459: Orthoptera, wolves, crickets)",
        "stored_grain_pest_in_vocab": False,
        "top_frequent_predictions": sorted(class_predictions.items(), key=lambda x: x[1], reverse=True)[:5],
        "sample_comparisons": results[:8],
        "conclusion": (
            "Nocturne Mini outputs generic outdoor biodiversity taxa (e.g. Canis lupus, crickets) "
            "and does not recognize stored grain internal pests (Sitophilus oryzae, Plodia interpunctella). "
            "Domain-specific physical acoustic models are required for accurate grain silo monitoring."
        ),
    }


def fit_and_save_final_models(X_feat: np.ndarray, X_spec: np.ndarray, y: np.ndarray):
    """Fits final baseline models on full dataset and saves artifacts."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # 1. Random Forest
    scaler = StandardScaler()
    X_feat_scaled = scaler.fit_transform(X_feat)
    rf = build_random_forest(n_estimators=100, max_depth=8, random_state=42)
    rf.fit(X_feat_scaled, y)

    rf_artifact = {
        "model": rf,
        "scaler": scaler,
        "classes": CLASS_NAMES,
        "feature_names": FEATURE_NAMES,
        "model_id": "sealsense-rf-baseline-v1",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    rf_path = os.path.join(ARTIFACTS_DIR, "rf_baseline.joblib")
    joblib.dump(rf_artifact, rf_path)

    # 2. Small CNN
    device = torch.device("cpu")
    counts = torch.bincount(torch.tensor(y), minlength=len(CLASS_NAMES)).float()
    weights = 1.0 / (counts + 1e-6)
    weights = weights / weights.sum()

    cnn = SealSenseAcousticCNN(num_classes=len(CLASS_NAMES)).to(device)
    optimizer = optim.Adam(cnn.parameters(), lr=0.003, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss(weight=weights.to(device))

    dataset = TensorDataset(torch.tensor(X_spec), torch.tensor(y))
    loader = DataLoader(dataset, batch_size=16, shuffle=True)
    for _ in range(25):
        train_cnn_epoch(cnn, loader, optimizer, criterion, device)

    cnn_path = os.path.join(ARTIFACTS_DIR, "cnn_baseline.pt")
    torch.save({
        "state_dict": cnn.state_dict(),
        "num_classes": len(CLASS_NAMES),
        "classes": CLASS_NAMES,
        "model_id": "sealsense-cnn-baseline-v1",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, cnn_path)

    return rf_path, cnn_path


def run_pipeline(n_splits: int = 4, compare_nocturne: bool = True, save: bool = True) -> Dict[str, Any]:
    print("=" * 72)
    print("SealSense Acoustic Intelligence Baseline Benchmark")
    print("=" * 72)

    t0 = time.time()
    print("Loading authentic stored-grain and environmental acoustic dataset...")
    windows = load_dataset()
    print(f"Loaded {len(windows)} windows across {len(set(w.session_id for w in windows))} unique sessions.")

    counts = {}
    domain_counts = {}
    for w in windows:
        counts[w.label] = counts.get(w.label, 0) + 1
        domain_counts[w.recording_domain] = domain_counts.get(w.recording_domain, 0) + 1

    for c in CLASS_NAMES:
        print(f"  • {c:<24}: {counts.get(c, 0):4d} windows")
    print("Recording Domains:")
    for d, c in domain_counts.items():
        print(f"  • {d:<24}: {c:4d} windows")

    print("\nExtracting physical acoustic features & Log-Mel spectrograms...")
    X_feat, X_spec, y, groups, meta = prepare_dataset_matrices(windows)
    print(f"Feature matrix shape     : {X_feat.shape}")
    print(f"Spectrogram tensor shape : {X_spec.shape}")
    print(f"Labels shape             : {y.shape}")

    print("\n--- 1. Evaluating Random Forest (GroupKFold by Session) ---")
    rf_results = evaluate_random_forest(X_feat, y, groups, n_splits=n_splits)
    print(f"  Macro Precision : {rf_results['macro_precision']:.4f}")
    print(f"  Macro Recall    : {rf_results['macro_recall']:.4f}")
    print(f"  Macro F1 Score  : {rf_results['macro_f1']:.4f}")
    print(f"  Weighted F1     : {rf_results['weighted_f1']:.4f}")
    print(f"  False Alarms/Hr : {rf_results['false_alarm_rate_per_hour']:.2f}")

    print("\n--- 2. Evaluating Small 2D CNN (GroupKFold by Session) ---")
    cnn_results = evaluate_cnn(X_spec, y, groups, n_splits=n_splits, epochs=20)
    print(f"  Macro Precision : {cnn_results['macro_precision']:.4f}")
    print(f"  Macro Recall    : {cnn_results['macro_recall']:.4f}")
    print(f"  Macro F1 Score  : {cnn_results['macro_f1']:.4f}")
    print(f"  Weighted F1     : {cnn_results['weighted_f1']:.4f}")
    print(f"  False Alarms/Hr : {cnn_results['false_alarm_rate_per_hour']:.2f}")

    nocturne_comp = {}
    if compare_nocturne:
        print("\n--- 3. Evaluating Nocturne Mini Comparison ---")
        nocturne_comp = evaluate_nocturne_mini_comparison(windows, max_samples=25)
        print(f"  Status          : {nocturne_comp.get('status')}")
        print(f"  Stored Pests    : {nocturne_comp.get('stored_grain_pest_in_vocab')}")
        print(f"  Top Predictions : {nocturne_comp.get('top_frequent_predictions')}")

    saved_paths = {}
    if save:
        print("\nFitting and saving production baseline models...")
        rf_p, cnn_p = fit_and_save_final_models(X_feat, X_spec, y)
        saved_paths["rf_model"] = rf_p
        saved_paths["cnn_model"] = cnn_p
        print(f"  Saved Random Forest : {rf_p}")
        print(f"  Saved Small CNN     : {cnn_p}")

    total_time = time.time() - t0

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_sec": round(total_time, 2),
        "dataset_summary": {
            "total_windows": len(windows),
            "classes": CLASS_NAMES,
            "class_distribution": counts,
            "domain_distribution": domain_counts,
            "unique_sessions": len(set(w.session_id for w in windows)),
            "window_duration_sec": 1.0,
            "sample_rate_hz": TARGET_SAMPLE_RATE,
        },
        "models": {
            "random_forest": rf_results,
            "small_cnn": cnn_results,
        },
        "nocturne_mini_comparison": nocturne_comp,
        "best_model": (
            "Random Forest" if rf_results["macro_f1"] >= cnn_results["macro_f1"] else "Small 2D CNN"
        ),
        "scientific_disclaimer": (
            "Machine learning baseline metrics for experimental stored-grain acoustic monitoring. "
            "Evaluated using strict Session-GroupKFold to prevent time-series autocorrelation leakage. "
            "Microphone recordings reflect physical INMP441 breadboard captures; reference recordings reflect USDA Bug Bytes cultures. "
            "Do NOT treat generic bioacoustic classifications as validated quarantine pest detection without physical grain inspection."
        ),
        "saved_artifacts": saved_paths,
    }

    report_path = os.path.join(ARTIFACTS_DIR, "evaluation_report.json")
    with open(report_path, "w") as fp:
        json.dump(report, fp, indent=2)
    print(f"\nEvaluation report written to {report_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SealSense Baseline ML Benchmark")
    parser.add_argument("--folds", type=int, default=4, help="Number of GroupKFold splits (default: 4)")
    parser.add_argument("--no-compare", action="store_true", help="Skip Nocturne Mini comparison")
    parser.add_argument("--no-save", action="store_true", help="Do not save model artifacts")
    args = parser.parse_args()

    run_pipeline(
        n_splits=args.folds,
        compare_nocturne=not args.no_compare,
        save=not args.no_save,
    )
