"""
Mock MQTT Sensor Publisher for AI-Based Predictive Maintenance System.
Simulates ESP32 edge node publishing 1 Hz vibration and temperature data.

Usage:
    python mock_publisher.py --mode normal
    python mock_publisher.py --mode fault_inner
    python mock_publisher.py --mode cycle       # Automatically transitions: Healthy -> Warning -> Critical -> Healthy
"""

import time
import json
import math
import random
import argparse
import paho.mqtt.client as mqtt

# Default MQTT broker configuration
DEFAULT_BROKER = "localhost"
DEFAULT_PORT = 1883
TOPIC_VIBRATION = "sensor/vibration"
TOPIC_TEMPERATURE = "sensor/temperature"


def generate_reading(mode: str, step: int, base_temp: float = 30.0):
    """
    Generates synthetic 3-axis vibration (in g) and temperature (in °C).
    |a| = sqrt(x^2 + y^2 + z^2)
    In normal condition: z ≈ 0.98g (gravity), x and y have small random noise (~0.02g).
    In fault conditions: impacts, harmonics, and elevated temperature are injected.
    """
    t = step * 0.1  # pseudo time
    current_ms = int(time.time() * 1000)

    if mode == "normal":
        # Healthy baseline motor running smoothly
        x = 0.02 * math.sin(2 * math.pi * 5 * t) + random.gauss(0, 0.015)
        y = 0.02 * math.cos(2 * math.pi * 5 * t) + random.gauss(0, 0.015)
        z = 0.98 + 0.03 * math.sin(2 * math.pi * 10 * t) + random.gauss(0, 0.02)
        temp = base_temp + random.uniform(-0.3, 0.3)

    elif mode == "warning":
        # Developing fault: noticeable vibration elevation, intermittent impulses
        impact = 0.35 if (step % 8 == 0) else 0.0
        x = 0.15 * math.sin(2 * math.pi * 12 * t) + impact + random.gauss(0, 0.04)
        y = 0.12 * math.cos(2 * math.pi * 12 * t) + random.gauss(0, 0.04)
        z = 0.98 + 0.18 * math.sin(2 * math.pi * 20 * t) + impact + random.gauss(0, 0.05)
        temp = base_temp + 8.0 + (step * 0.05) + random.uniform(-0.5, 0.5)

    elif mode in ("critical", "fault_inner", "fault_outer", "fault_ball"):
        # Severe bearing fault: strong shock pulses, elevated RMS, high kurtosis, temperature runaway
        impact = 1.2 if (step % 4 == 0) else 0.0
        harmonic = 0.5 * math.sin(2 * math.pi * 35 * t)
        x = 0.45 * math.sin(2 * math.pi * 25 * t) + harmonic + impact + random.gauss(0, 0.15)
        y = 0.40 * math.cos(2 * math.pi * 25 * t) + impact + random.gauss(0, 0.15)
        z = 0.98 + 0.60 * math.sin(2 * math.pi * 50 * t) + impact + random.gauss(0, 0.20)
        temp = base_temp + 22.0 + random.uniform(-0.8, 0.8)

    else:
        # Default fallback
        x, y, z = random.gauss(0, 0.02), random.gauss(0, 0.02), 0.98 + random.gauss(0, 0.02)
        temp = base_temp

    vib_payload = {
        "x": round(x, 4),
        "y": round(y, 4),
        "z": round(z, 4),
        "timestamp": current_ms
    }

    temp_payload = {
        "temp": round(temp, 2),
        "timestamp": current_ms
    }

    return vib_payload, temp_payload


def run_publisher(broker: str, port: int, mode: str, rate_hz: float = 1.0):
    client = mqtt.Client(client_id="Mock_ESP32_Publisher")
    
    print(f"Connecting to MQTT broker at {broker}:{port}...")
    try:
        client.connect(broker, port, 60)
        client.loop_start()
        print(f"[CONNECTED] Publishing simulated telemetry to topics:")
        print(f"  - {TOPIC_VIBRATION}")
        print(f"  - {TOPIC_TEMPERATURE}")
        print(f"  Mode: {mode}, Rate: {rate_hz} Hz\n")
    except Exception as e:
        print(f"[ERROR] Failed to connect to broker {broker}:{port}: {e}")
        print("Ensure Mosquitto or HiveMQ broker is running, or specify --broker <host>.")
        return

    step = 0
    interval = 1.0 / rate_hz
    base_temp = 31.0

    try:
        while True:
            # Handle cycle mode: Healthy (30s) -> Warning (20s) -> Critical (20s) -> Repeat
            active_mode = mode
            if mode == "cycle":
                cycle_step = step % 70
                if cycle_step < 30:
                    active_mode = "normal"
                elif cycle_step < 50:
                    active_mode = "warning"
                else:
                    active_mode = "critical"

            vib, temp = generate_reading(active_mode, step, base_temp)
            
            client.publish(TOPIC_VIBRATION, json.dumps(vib))
            client.publish(TOPIC_TEMPERATURE, json.dumps(temp))

            mag = math.sqrt(vib["x"]**2 + vib["y"]**2 + vib["z"]**2)
            print(f"[{active_mode.upper():8s}] Step {step:04d} | |a|={mag:.3f}g (x={vib['x']:.2f}, y={vib['y']:.2f}, z={vib['z']:.2f}) | Temp={temp['temp']}°C")

            step += 1
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nStopping mock publisher...")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock ESP32 Sensor Publisher for Predictive Maintenance")
    parser.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT broker port (default: 1883)")
    parser.add_argument("--mode", default="cycle", choices=["normal", "warning", "critical", "fault_inner", "fault_outer", "fault_ball", "cycle"], help="Simulation mode")
    parser.add_argument("--rate", type=float, default=1.0, help="Publish rate in Hz (default: 1.0)")
    args = parser.parse_args()

    run_publisher(args.broker, args.port, args.mode, args.rate)
