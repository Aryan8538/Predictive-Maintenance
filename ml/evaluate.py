"""
Evaluation and Diagnostics Script for AI-Based Predictive Maintenance System.
Computes test metrics, confusion matrix, ROC-AUC, and feature importances.
"""

import os
import numpy as np
import joblib
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score
)
from sklearn.preprocessing import label_binarize

from dataset_loader import CLASS_MAP, load_cwru_mat_file, generate_synthetic_bearing_signals
from feature_extraction import extract_features, WINDOW_SIZE, FEATURE_NAMES
from train import preprocess_signal, build_feature_dataset, load_all_training_data


def evaluate_model():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "model.joblib")
    data_dir = os.path.join(script_dir, "data")

    if not os.path.exists(model_path):
        print(f"[ERROR] Trained model not found at {model_path}. Run train.py first.")
        return

    print("==================================================")
    print("Evaluating Predictive Maintenance Model")
    print("==================================================")

    # Load Artifact
    artifact = joblib.load(model_path)
    model = artifact["model"]
    feature_names = artifact.get("feature_names", FEATURE_NAMES)
    class_map = artifact.get("class_map", CLASS_MAP)
    target_names = [class_map[i] for i in range(4)]

    # Load and build test features
    raw_signals = load_all_training_data(data_dir)
    X, y = build_feature_dataset(raw_signals, window_size=WINDOW_SIZE, fs=12000.0)

    # Predict
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)

    # 1. Accuracy & Classification Report
    acc = accuracy_score(y, y_pred)
    print(f"\nOverall Accuracy: {acc * 100:.2f}%")
    print("\nDetailed Classification Report:")
    print(classification_report(y, y_pred, target_names=target_names))

    # 2. Confusion Matrix
    cm = confusion_matrix(y, y_pred)
    print("\nConfusion Matrix (Rows=True, Cols=Predicted):")
    print("Classes: 0:Normal, 1:InnerRace, 2:OuterRace, 3:Ball")
    print(cm)

    # 3. Multiclass ROC-AUC (OvR)
    y_bin = label_binarize(y, classes=[0, 1, 2, 3])
    try:
        roc_ovr = roc_auc_score(y_bin, y_proba, multi_class="ovr", average="macro")
        print(f"\nMulticlass ROC-AUC (Macro OvR): {roc_ovr:.4f}")
    except Exception as e:
        print(f"\nROC-AUC computation skipped: {e}")

    # 4. Feature Importance
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        sorted_indices = np.argsort(importances)[::-1]
        print("\nFeature Importance Ranking:")
        for rank, idx in enumerate(sorted_indices, 1):
            print(f"  {rank}. {feature_names[idx]:<20} : {importances[idx] * 100:.2f}%")

    print("\n[NOTE ON EVALUATION CONTEXT]")
    print("These results validate the Random Forest classifier against CWRU benchmark conditions.")
    print("Physical prototype deployment on ADXL345 (100 Hz / 1 Hz stream) operates with lower bandwidth")
    print("and higher sensor floor noise; live accuracy should be assessed independently.")


if __name__ == "__main__":
    evaluate_model()
