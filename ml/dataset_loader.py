"""
Dataset Loader for CWRU and NASA IMS Bearing Datasets.
Supports downloading canonical CWRU .mat files and provides synthetic bearing signal fallbacks.

CWRU 12kHz Drive End (DE) standard benchmarks:
  - Normal Baseline: 97.mat
  - Inner Race Fault (7 mil): 105.mat
  - Ball Fault (7 mil): 118.mat
  - Outer Race Fault (7 mil, centered @ 6:00): 130.mat
"""

import os
import urllib.request
import numpy as np
from scipy import io

# Official CWRU Bearing Data Center URLs
CWRU_URLS = {
    "normal": "https://engineering.case.edu/sites/default/files/97.mat",
    "inner_race": "https://engineering.case.edu/sites/default/files/105.mat",
    "ball": "https://engineering.case.edu/sites/default/files/118.mat",
    "outer_race": "https://engineering.case.edu/sites/default/files/130.mat"
}

CLASS_MAP = {
    0: "Normal",
    1: "Inner Race Fault",
    2: "Outer Race Fault",
    3: "Ball Fault"
}


def download_cwru_dataset(dest_dir: str):
    """
    Downloads canonical CWRU .mat files into dest_dir if not already present.
    """
    os.makedirs(dest_dir, exist_ok=True)
    for fault_type, url in CWRU_URLS.items():
        fname = os.path.basename(url)
        target_path = os.path.join(dest_dir, fname)
        if not os.path.exists(target_path):
            print(f"Downloading {fname} from CWRU ({fault_type})...")
            try:
                urllib.request.urlretrieve(url, target_path)
                print(f"[OK] Downloaded {fname}")
            except Exception as e:
                print(f"[WARN] Failed to download {fname}: {e}")
        else:
            print(f"[EXISTS] {fname} already in {dest_dir}")


def load_cwru_mat_file(file_path: str) -> np.ndarray:
    """
    Loads raw drive-end accelerometer time series from a CWRU .mat file.
    """
    data = io.loadmat(file_path)
    # Search for DE (Drive End) time series key
    for k in data.keys():
        if "DE_time" in k:
            return data[k].flatten()
    # Fallback to any array key ending with time
    for k in data.keys():
        if k.endswith("_time"):
            return data[k].flatten()
    raise ValueError(f"No vibration time series found in {file_path}")


def generate_synthetic_bearing_signals(n_samples: int = 40000, fs: float = 12000.0) -> dict:
    """
    Generates physically modeled synthetic vibration signals for the 4 classes
    based on bearing defect kinematics (shaft speed ~1797 RPM = ~29.95 Hz):
      - BPFI (Ball Pass Frequency Inner race) ~ 5.4 * fr ≈ 161.7 Hz
      - BPFO (Ball Pass Frequency Outer race) ~ 3.6 * fr ≈ 107.8 Hz
      - BSF (Ball Spin Frequency) ~ 2.3 * fr ≈ 68.9 Hz

    Used as an offline fixture if raw CWRU files are not yet downloaded.
    """
    t = np.linspace(0, n_samples / fs, n_samples, endpoint=False)
    fr = 29.95  # Shaft rotational frequency (~1797 RPM)

    # 1. Normal: shaft harmonics + low Gaussian background noise
    normal = (
        0.08 * np.sin(2 * np.pi * fr * t)
        + 0.04 * np.sin(2 * np.pi * 2 * fr * t)
        + np.random.normal(0, 0.03, n_samples)
    )

    # 2. Inner Race: BPFI impacts with shaft frequency amplitude modulation
    bpfi = 5.415 * fr
    mod = 1.0 + 0.8 * np.cos(2 * np.pi * fr * t)
    carrier_inner = np.sin(2 * np.pi * 3200 * t) * np.exp(-((t % (1.0 / bpfi)) * 3000))
    inner = (
        normal
        + 0.65 * mod * carrier_inner
        + 0.15 * np.sin(2 * np.pi * bpfi * t)
        + np.random.normal(0, 0.06, n_samples)
    )

    # 3. Outer Race: BPFO impacts without shaft modulation
    bpfo = 3.585 * fr
    carrier_outer = np.sin(2 * np.pi * 3000 * t) * np.exp(-((t % (1.0 / bpfo)) * 2500))
    outer = (
        normal
        + 0.70 * carrier_outer
        + 0.20 * np.sin(2 * np.pi * bpfo * t)
        + np.random.normal(0, 0.06, n_samples)
    )

    # 4. Ball Fault: 2 * BSF impacts with fundamental train cage modulation
    bsf = 2.32 * fr
    ftf = 0.38 * fr
    mod_cage = 1.0 + 0.5 * np.cos(2 * np.pi * ftf * t)
    carrier_ball = np.sin(2 * np.pi * 2800 * t) * np.exp(-((t % (1.0 / (2 * bsf))) * 2200))
    ball = (
        normal
        + 0.55 * mod_cage * carrier_ball
        + np.random.normal(0, 0.08, n_samples)
    )

    return {
        0: normal,
        1: inner,
        2: outer,
        3: ball
    }
