"""
Feature Extraction Module for Backend Inference.
Identical mathematical implementation to ml/feature_extraction.py.

Window Size: 256 samples
Features:
    1. RMS (Root Mean Square)
    2. Peak value (max absolute amplitude)
    3. Crest factor (peak / RMS)
    4. Kurtosis
    5. Skewness
    6. Standard deviation
    7. FFT dominant frequency
    8. Spectral energy
    9. Spectral entropy
"""

import numpy as np
from scipy import stats

FEATURE_NAMES = [
    "rms",
    "peak",
    "crest_factor",
    "kurtosis",
    "skewness",
    "std",
    "fft_dominant_freq",
    "spectral_energy",
    "spectral_entropy"
]

WINDOW_SIZE = 256
DEFAULT_SAMPLING_RATE_HZ = 100.0


def compute_magnitude(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """
    Computes Euclidean magnitude: |a| = sqrt(x^2 + y^2 + z^2)
    """
    return np.sqrt(x**2 + y**2 + z**2)


def extract_features(signal: np.ndarray, sampling_rate: float = DEFAULT_SAMPLING_RATE_HZ) -> np.ndarray:
    """
    Extracts the 9 canonical features from a 1D vibration signal array of length N (typically 256).

    Args:
        signal: 1D numpy array of vibration amplitude or magnitude.
        sampling_rate: Sampling frequency in Hz (default: 100.0 Hz).

    Returns:
        np.ndarray: Array of 9 extracted features in exact required order.
    """
    signal = np.asarray(signal, dtype=np.float64)
    eps = 1e-12
    n = len(signal)
    if n == 0:
        return np.zeros(len(FEATURE_NAMES), dtype=np.float64)

    # 1. RMS - sqrt(mean(x^2))
    rms = np.sqrt(np.mean(signal**2))

    # 2. Peak value - max absolute amplitude
    peak = np.max(np.abs(signal))

    # 3. Crest factor - peak / RMS
    crest_factor = peak / (rms + eps)

    # 4 & 5. Kurtosis and Skewness
    signal_std = float(np.std(signal, ddof=1)) if n > 1 else 0.0
    if signal_std > 1e-6:
        kurt = float(stats.kurtosis(signal, fisher=True, bias=False))
        skew = float(stats.skew(signal, bias=False))
    else:
        kurt = 0.0
        skew = 0.0

    # 6. Standard deviation
    std = signal_std

    # Frequency Domain Features via FFT
    signal_centered = signal - np.mean(signal)
    fft_vals = np.fft.rfft(signal_centered)
    fft_mags = np.abs(fft_vals)
    fft_freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate)

    if len(fft_mags) > 1:
        dominant_idx = np.argmax(fft_mags[1:]) + 1
        fft_dominant_freq = float(fft_freqs[dominant_idx])
    else:
        fft_dominant_freq = 0.0

    # 8. Spectral energy - sum of squared FFT magnitudes
    spectral_energy = float(np.sum(fft_mags**2))

    # 9. Spectral entropy - H = -sum(p_i * log2(p_i)) where p_i is normalized power
    power_spectrum = fft_mags**2
    sum_power = np.sum(power_spectrum)
    if sum_power > eps:
        p_i = power_spectrum / sum_power
        p_i_nonzero = p_i[p_i > eps]
        spectral_entropy = float(-np.sum(p_i_nonzero * np.log2(p_i_nonzero)))
    else:
        spectral_entropy = 0.0

    return np.array([
        rms,
        peak,
        crest_factor,
        kurt,
        skew,
        std,
        fft_dominant_freq,
        spectral_energy,
        spectral_entropy
    ], dtype=np.float64)


def extract_features_dict(signal: np.ndarray, sampling_rate: float = DEFAULT_SAMPLING_RATE_HZ) -> dict:
    """
    Returns the extracted features as a dictionary with named keys.
    """
    feature_arr = extract_features(signal, sampling_rate)
    return dict(zip(FEATURE_NAMES, feature_arr))
