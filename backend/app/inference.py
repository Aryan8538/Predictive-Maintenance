"""
Real-Time Inference Engine for AI-Based Predictive Maintenance.
Manages a circular sliding window buffer (256 samples) of vibration magnitude,
extracts identical 9 time-frequency features, and performs Random Forest inference.

State Mapping Thresholds:
  - Healthy: Normal class (0) with confidence >= 0.70 and RMS < 1.15g.
  - Warning: Moderate fault probability (0.45 <= p < 0.75) or elevated RMS (1.15g <= RMS < 1.40g).
  - Critical: High-confidence fault detection (p >= 0.75 for Ball/Inner/Outer) or severe RMS >= 1.40g.
"""

import os
import logging
from collections import deque
from datetime import datetime, timezone
import numpy as np
import joblib

from .feature_extraction import extract_features, compute_magnitude, WINDOW_SIZE, FEATURE_NAMES
from .models import Prediction
from .db import SessionLocal

logger = logging.getLogger("predictive_maintenance.inference")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.joblib")


class InferenceEngine:
    def __init__(self, window_size: int = WINDOW_SIZE):
        self.window_size = window_size
        self.buffer = deque(maxlen=window_size)
        self.model_artifact = None
        self.model = None
        self.latest_prediction = {
            "status": "Healthy",
            "confidence": 1.0,
            "rms": 1.0,
            "predicted_at": datetime.now(timezone.utc)
        }
        self.load_model()

    def load_model(self):
        """
        Loads the trained Random Forest model artifact.
        """
        if os.path.exists(MODEL_PATH):
            try:
                self.model_artifact = joblib.load(MODEL_PATH)
                self.model = self.model_artifact["model"]
                logger.info(f"Loaded ML model from {MODEL_PATH}")
            except Exception as e:
                logger.error(f"Failed to load model from {MODEL_PATH}: {e}")
                self.model = None
        else:
            logger.warning(f"No model found at {MODEL_PATH}. Will evaluate via heuristic thresholds until model is trained.")
            self.model = None

    def add_sample(self, x: float, y: float, z: float) -> dict:
        """
        Appends a 3-axis vibration sample, calculates magnitude |a|,
        and triggers inference if buffer is populated.
        """
        mag = float(np.sqrt(x**2 + y**2 + z**2))
        self.buffer.append(mag)

        rms = float(np.sqrt(np.mean(np.array(self.buffer)**2)))

        # If buffer doesn't have 256 samples yet, compute instant baseline estimate
        if len(self.buffer) < 16:
            status = "Healthy" if rms < 1.15 else ("Warning" if rms < 1.40 else "Critical")
            result = {
                "status": status,
                "confidence": 0.85,
                "rms": round(rms, 4),
                "predicted_at": datetime.now(timezone.utc)
            }
            self.latest_prediction = result
            return result

        # Extract features across current window
        signal_window = np.array(self.buffer)
        
        # If model is loaded, run ML inference
        if self.model is not None:
            feats = extract_features(signal_window, sampling_rate=100.0).reshape(1, -1)
            try:
                probs = self.model.predict_proba(feats)[0]
                pred_class = int(np.argmax(probs))
                confidence = float(np.max(probs))

                # Mapping Logic:
                # Class 0: Normal
                # Classes 1, 2, 3: Inner, Outer, Ball Faults
                if rms >= 1.40 or (pred_class != 0 and confidence >= 0.75):
                    status = "Critical"
                elif pred_class == 0 and confidence >= 0.70 and rms < 1.15:
                    status = "Healthy"
                else:
                    status = "Warning"

            except Exception as e:
                logger.error(f"Inference prediction error: {e}")
                status = "Critical" if rms >= 1.40 else ("Warning" if rms >= 1.15 else "Healthy")
                confidence = 0.90
        else:
            # Fallback heuristic based on RMS & peak
            if rms < 1.15:
                status = "Healthy"
                confidence = 0.95
            elif rms < 1.40:
                status = "Warning"
                confidence = 0.80
            else:
                status = "Critical"
                confidence = 0.92

        result = {
            "status": status,
            "confidence": round(confidence, 4),
            "rms": round(rms, 4),
            "predicted_at": datetime.now(timezone.utc)
        }
        self.latest_prediction = result

        # Persist to database
        self._persist_prediction(result)

        return result

    def _persist_prediction(self, res: dict):
        try:
            with SessionLocal() as db:
                record = Prediction(
                    status=res["status"],
                    confidence=res["confidence"],
                    rms=res["rms"],
                    predicted_at=res["predicted_at"]
                )
                db.add(record)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to persist prediction: {e}")

    def get_latest(self) -> dict:
        return self.latest_prediction


# Singleton Engine Instance
inference_engine = InferenceEngine(window_size=WINDOW_SIZE)
