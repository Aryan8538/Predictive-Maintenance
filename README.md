# AI-Based Predictive Maintenance System

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-336791?logo=postgresql)](https://www.postgresql.org/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?logo=react)](https://vitejs.dev/)
[![Scikit-Learn](https://img.shields.io/badge/ML-Random%20Forest-F7931E?logo=scikit-learn)](https://scikit-learn.org/)
[![ESP32](https://img.shields.io/badge/Microcontroller-ESP32%20DevKit%20V1-E7352C)](https://www.espressif.com/)

Final Year B.Tech Major Project (CSE - IoT)  
**Institution:** Raj Kumar Goel Institute of Technology (RKGIT), Ghaziabad (AKTU affiliated)

---

## 1. System Overview

An Industrial IoT condition monitoring and predictive maintenance system. An ESP32 edge node acquires real-time vibration ($x, y, z$ accelerations via ADXL345) and machine temperature (DS18B20 1-Wire) at 1 Hz, publishing structured telemetry over MQTT. 

A Python FastAPI backend ingests the MQTT stream into PostgreSQL, computes 9 signal processing features across a 256-sample window of vibration magnitude, runs inference through an offline-trained Scikit-Learn Random Forest Classifier, and streams machine health state (`Healthy`, `Warning`, `Critical`) to a modern React dashboard over WebSockets.

> **Evaluation Context Separation:**
> - **Laboratory Model Accuracy (92–98%):** Trained and validated on laboratory-grade vibration datasets (CWRU Bearing Data Center at 12/48 kHz, NASA IMS).
> - **Edge Prototype Accuracy:** Real-time acquisition using low-cost MEMS hardware (ADXL345 over I2C at 1 Hz). Results on the physical prototype are evaluated and reported separately due to sensor bandwidth differences.

---

## 2. Hardware Pinout & Wiring

| Sensor | Sensor Pin | ESP32 GPIO | Description / Notes |
|---|---|---|---|
| **ADXL345** | VCC | 3.3V | Digital 3-axis accelerometer |
| | GND | GND | Ground |
| | SDA | GPIO 21 | I2C Data line |
| | SCL | GPIO 22 | I2C Clock line |
| **DS18B20** | VCC | 3.3V | 1-Wire digital temperature sensor |
| | GND | GND | Ground |
| | DATA | GPIO 4 | Requires 10 kΩ pull-up resistor to 3.3V |

---

## 3. MQTT Data Contracts

- **Broker Default:** `localhost:1883` or Cloud Broker (e.g., HiveMQ Cloud)
- **Publish Rate:** 1 Hz

| Topic | Publisher | Format | Payload Example |
|---|---|---|---|
| `sensor/vibration` | ESP32 / Mock | JSON | `{"x": 0.02, "y": 0.01, "z": 0.98, "timestamp": 1774941200000}` |
| `sensor/temperature` | ESP32 / Mock | JSON | `{"temp": 34.5, "timestamp": 1774941200000}` |
| `prediction/result` | Backend | JSON | `{"status": "Healthy", "confidence": 0.96, "rms": 0.981}` |

---

## 4. Repository Layout

```
predictive-maintenance/
├── firmware/
│   └── esp32_sensor_node/
│       ├── esp32_sensor_node.ino    # ESP32 firmware (ADXL345 + DS18B20)
│       └── secrets.h.example        # Wi-Fi & MQTT credentials template
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app & WebSockets
│   │   ├── mqtt_subscriber.py       # paho-mqtt client background worker
│   │   ├── feature_extraction.py    # Time & frequency feature extraction (shared math)
│   │   ├── models.py                # SQLAlchemy DB models & Pydantic schemas
│   │   ├── db.py                    # PostgreSQL engine & session management
│   │   └── inference.py             # Sliding window & Random Forest inference
│   ├── mock_publisher.py            # Simulated sensor & fault injection script
│   ├── requirements.txt
│   └── .env.example
├── ml/
│   ├── data/                        # CWRU & NASA IMS datasets
│   ├── notebooks/                   # Exploratory analysis
│   ├── feature_extraction.py        # Shared feature logic (identical to backend)
│   ├── train.py                     # CWRU pipeline & GridSearchCV
│   ├── evaluate.py                  # Confusion matrix, ROC-AUC, classification report
│   └── requirements.txt
├── dashboard/                       # React + Vite industrial health dashboard
├── docs/                            # Synopsis & IEEE conference paper drafts
└── README.md
```

---

## 5. Quickstart & Testing

### 1. Backend & Mock Sensor Publisher
```bash
# In backend/
cd backend
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Run FastAPI Server
uvicorn app.main:app --reload --port 8000

# In a separate terminal, launch mock publisher (simulates edge hardware)
python mock_publisher.py --mode normal
# To simulate bearing fault:
python mock_publisher.py --mode fault
```

### 2. React Dashboard
```bash
# In dashboard/
cd dashboard
npm install
npm run dev
```

### 3. ML Model Training & Evaluation
```bash
# In ml/
cd ml
pip install -r requirements.txt
python train.py
python evaluate.py
```
