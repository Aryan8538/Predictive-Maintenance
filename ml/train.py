"""
Model Training Pipeline for AI-Based Predictive Maintenance System.
Trains a Scikit-Learn RandomForestClassifier on CWRU Bearing Data.

Preprocessing:
  1. Z-score normalization & moving-average smoothing
  2. 256-sample window segmentation
  3. 9-feature extraction (time & frequency domain)

Optimization:
  GridSearchCV with 5-fold cross validation.

Exports:
  ml/model.joblib and backend/app/model.joblib
"""

import os
import shutil
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import classification_report, accuracy_score
import joblib

from feature_extraction import extract_features, WINDOW_SIZE, FEATURE_NAMES
from dataset_loader import (
    CWRU_URLS,
    CLASS_MAP,
    download_cwru_dataset,
    load_cwru_mat_file,
    generate_synthetic_bearing_signals
)


def preprocess_signal(signal: np.ndarray, window_len: int = 5) -> np.ndarray:
    """
    Applies Z-score normalization and moving-average smoothing.
    """
    # 1. Z-score normalization
    mean = np.mean(signal)
    std = np.std(signal)
    norm_signal = (signal - mean) / (std + 1e-12)

    # 2. Moving average smoothing
    if window_len > 1:
        box = np.ones(window_len) / window_len
        smoothed = np.convolve(norm_signal, box, mode="same")
        return smoothed
    return norm_signal


def build_feature_dataset(raw_signals: dict, window_size: int = WINDOW_SIZE, fs: float = 12000.0):
    """
    Segments raw 1D continuous vibration arrays into windows and computes the 9 features per window.
    """
    X_list = []
    y_list = []

    for class_id, signal in raw_signals.items():
        processed = preprocess_signal(signal)
        n_windows = len(processed) // window_size

        for i in range(n_windows):
            start = i * window_size
            end = start + window_size
            window = processed[start:end]

            feats = extract_features(window, sampling_rate=fs)
            X_list.append(feats)
            y_list.append(class_id)

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list, dtype=np.int64)
    return X, y


def load_all_training_data(data_dir: str):
    """
    Attempts to load downloaded CWRU .mat files; if not found, falls back to high-fidelity simulated bearing data.
    """
    file_mapping = {
        0: "97.mat",   # Normal baseline
        1: "105.mat",  # Inner race
        2: "130.mat",  # Outer race
        3: "118.mat"   # Ball
    }

    raw_signals = {}
    all_files_exist = all(
        os.path.exists(os.path.join(data_dir, fname)) for fname in file_mapping.values()
    )

    if all_files_exist:
        print("[DATA] Loading CWRU .mat files from:", data_dir)
        for class_id, fname in file_mapping.items():
            path = os.path.join(data_dir, fname)
            raw_signals[class_id] = load_cwru_mat_file(path)
            print(f"  Class {class_id} ({CLASS_MAP[class_id]}): {len(raw_signals[class_id])} samples")
    else:
        print("[DATA] CWRU .mat files not all present locally. Attempting download...")
        download_cwru_dataset(data_dir)
        # Check again
        all_now = all(
            os.path.exists(os.path.join(data_dir, fname)) for fname in file_mapping.values()
        )
        if all_now:
            for class_id, fname in file_mapping.items():
                path = os.path.join(data_dir, fname)
                raw_signals[class_id] = load_cwru_mat_file(path)
        else:
            print("[WARN] Network download unavailable or incomplete. Using calibrated synthetic kinematic fixtures for training.")
            raw_signals = generate_synthetic_bearing_signals(n_samples=50000, fs=12000.0)

    return raw_signals


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")
    model_output_path = os.path.join(script_dir, "model.joblib")
    backend_model_path = os.path.join(script_dir, "..", "backend", "app", "model.joblib")

    print("==================================================")
    print("AI-Based Predictive Maintenance: Training Pipeline")
    print("==================================================")

    # 1. Load Data
    raw_signals = load_all_training_data(data_dir)

    # 2. Extract Features
    print(f"\n[FEATURES] Extracting 9 time-frequency features (Window={WINDOW_SIZE})...")
    X, y = build_feature_dataset(raw_signals, window_size=WINDOW_SIZE, fs=12000.0)
    print(f"  Total feature vectors: {X.shape[0]} | Dimensions: {X.shape[1]}")
    for class_id, label in CLASS_MAP.items():
        count = np.sum(y == class_id)
        print(f"  Class {class_id} ({label}): {count} windows")

    # 3. Train/Test Split (80/20 stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"\n[SPLIT] Train samples: {X_train.shape[0]}, Test samples: {X_test.shape[0]}")

    # 4. Hyperparameter Search via GridSearchCV
    param_grid = {
        "n_estimators": [100, 200],
        "max_depth": [10, 20, None],
        "min_samples_split": [2, 5],
        "criterion": ["gini", "entropy"]
    }

    print("\n[HYPERPARAMETERS] Running GridSearchCV (5-Fold CV)...")
    base_rf = RandomForestClassifier(random_state=42, n_jobs=-1)
    grid_search = GridSearchCV(
        estimator=base_rf,
        param_grid=param_grid,
        cv=5,
        scoring="accuracy",
        n_jobs=-1,
        verbose=1
    )
    grid_search.fit(X_train, y_train)

    best_model = grid_search.best_estimator_
    print(f"\n[OPTIMAL] Best parameters found: {grid_search.best_params_}")
    print(f"  5-Fold CV Mean Score: {grid_search.best_score_:.4f}")

    # 5. Evaluate on Holdout Test Set
    y_pred = best_model.predict(X_test)
    test_acc = accuracy_score(y_test, y_pred)
    print(f"\n[EVALUATION] Holdout Test Accuracy: {test_acc * 100:.2f}%")
    print("\nClassification Report:")
    target_names = [CLASS_MAP[i] for i in range(4)]
    print(classification_report(y_test, y_pred, target_names=target_names))

    # Package metadata alongside model
    model_artifact = {
        "model": best_model,
        "feature_names": FEATURE_NAMES,
        "window_size": WINDOW_SIZE,
        "class_map": CLASS_MAP,
        "best_params": grid_search.best_params_,
        "test_accuracy": float(test_acc),
        "target_names": target_names
    }

    # 6. Save joblib artifact
    print(f"\n[SAVE] Exporting model to: {model_output_path}")
    joblib.dump(model_artifact, model_output_path)

    # Also deploy to backend/app/model.joblib
    os.makedirs(os.path.dirname(backend_model_path), exist_ok=True)
    shutil.copyfile(model_output_path, backend_model_path)
    print(f"[DEPLOY] Copied trained model to backend: {backend_model_path}")
    print("Training pipeline completed successfully.")


if __name__ == "__main__":
    main()
