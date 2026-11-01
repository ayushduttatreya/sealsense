"""
SealSense Baseline Acoustic Classification Architectures
=========================================================
Implements:
1. Random Forest Classifier on 22 extracted physical acoustic features.
2. Lightweight 2D CNN (PyTorch) on 64-band Log-Mel Spectrograms.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.ensemble import RandomForestClassifier

from .dataset import CLASS_NAMES


def build_random_forest(n_estimators: int = 100, max_depth: int = 8, random_state: int = 42) -> RandomForestClassifier:
    """Builds a balanced Random Forest model for physical feature classification."""
    return RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )


class SealSenseAcousticCNN(nn.Module):
    """
    Compact 2D Convolutional Neural Network for Log-Mel Spectrogram classification.
    Designed for fast, reproducible CPU inference on edge devices (~28k parameters).
    """
    def __init__(self, num_classes: int = len(CLASS_NAMES), dropout: float = 0.3):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(16)
        self.pool1 = nn.MaxPool2d(2, 2)

        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(32)
        self.pool2 = nn.MaxPool2d(2, 2)

        self.conv3 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(64)
        self.global_pool = nn.AdaptiveAvgPool2d((1, 1))

        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, 1, n_mels, time_steps)
        if x.dim() == 3:
            x = x.unsqueeze(1)

        x = self.pool1(F.relu(self.bn1(self.conv1(x))))
        x = self.pool2(F.relu(self.bn2(self.conv2(x))))
        x = F.relu(self.bn3(self.conv3(x)))
        x = self.global_pool(x)
        x = torch.flatten(x, 1)

        x = self.dropout(x)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            return F.softmax(logits, dim=-1)
