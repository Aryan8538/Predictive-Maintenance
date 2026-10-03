"""
MQTT Subscriber Service for Predictive Maintenance Backend.
Subscribes to sensor telemetry topics, persists readings, feeds the inference engine,
and broadcasts inference results back to MQTT.
"""

import os
import json
import logging
import threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

from .db import SessionLocal
from .models import SensorReading
from .inference import inference_engine

logger = logging.getLogger("predictive_maintenance.mqtt")

TOPIC_VIBRATION = "sensor/vibration"
TOPIC_TEMPERATURE = "sensor/temperature"
TOPIC_PREDICTION = "prediction/result"


class MQTTSubscriber:
    def __init__(self):
        self.broker = os.getenv("MQTT_BROKER", "127.0.0.1")
        self.port = int(os.getenv("MQTT_PORT", 1883))
        self.username = os.getenv("MQTT_USERNAME", "")
        self.password = os.getenv("MQTT_PASSWORD", "")
        self.client_id = os.getenv("MQTT_CLIENT_ID", "FastAPI_PredictiveMaintenance_Backend")

        self.client = mqtt.Client(client_id=self.client_id)
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self.latest_vibration = None
        self.latest_temperature = None
        self.broadcast_callback = None
        self._running = False

    def set_broadcast_callback(self, callback):
        """
        Registers a callback to push live updates to connected WebSocket clients.
        """
        self.broadcast_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker}:{self.port}")
            client.subscribe(TOPIC_VIBRATION)
            client.subscribe(TOPIC_TEMPERATURE)
            logger.info(f"Subscribed to {TOPIC_VIBRATION} and {TOPIC_TEMPERATURE}")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic = msg.topic

            if topic == TOPIC_VIBRATION:
                self._handle_vibration(payload)
            elif topic == TOPIC_TEMPERATURE:
                self._handle_temperature(payload)

        except Exception as e:
            logger.error(f"Error processing MQTT message on {msg.topic}: {e}")

    def _handle_vibration(self, payload: dict):
        x = float(payload.get("x", 0.0))
        y = float(payload.get("y", 0.0))
        z = float(payload.get("z", 0.0))
        ts_ms = payload.get("timestamp", int(datetime.now(timezone.utc).timestamp() * 1000))
        recorded_at = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

        self.latest_vibration = {
            "x": x,
            "y": y,
            "z": z,
            "timestamp": ts_ms
        }

        # 1. Persist to DB
        self._persist_reading(
            reading_type="vibration",
            x=x, y=y, z=z,
            temp=None,
            recorded_at=recorded_at
        )

        # 2. Feed to Inference Engine
        pred = inference_engine.add_sample(x, y, z)

        # 3. Publish prediction to MQTT
        pred_payload = {
            "status": pred["status"],
            "confidence": pred["confidence"],
            "rms": pred["rms"]
        }
        self.client.publish(TOPIC_PREDICTION, json.dumps(pred_payload))

        # 4. Notify WebSocket clients
        if self.broadcast_callback:
            stream_event = {
                "type": "vibration_and_prediction",
                "vibration": self.latest_vibration,
                "temperature": self.latest_temperature,
                "prediction": pred_payload
            }
            self.broadcast_callback(stream_event)

    def _handle_temperature(self, payload: dict):
        temp = float(payload.get("temp", 0.0))
        ts_ms = payload.get("timestamp", int(datetime.now(timezone.utc).timestamp() * 1000))
        recorded_at = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

        self.latest_temperature = {
            "temp": temp,
            "timestamp": ts_ms
        }

        # Persist to DB
        self._persist_reading(
            reading_type="temperature",
            x=None, y=None, z=None,
            temp=temp,
            recorded_at=recorded_at
        )

        # Notify WebSocket clients
        if self.broadcast_callback:
            stream_event = {
                "type": "temperature",
                "temperature": self.latest_temperature
            }
            self.broadcast_callback(stream_event)

    def _persist_reading(self, reading_type: str, x, y, z, temp, recorded_at):
        try:
            with SessionLocal() as db:
                record = SensorReading(
                    reading_type=reading_type,
                    x=x, y=y, z=z,
                    temp=temp,
                    recorded_at=recorded_at
                )
                db.add(record)
                db.commit()
        except Exception as e:
            logger.error(f"Failed to persist {reading_type} reading: {e}")

    def start(self):
        """
        Starts the MQTT client background loop.
        """
        if self._running:
            return
        self._running = True

        def _connect():
            try:
                logger.info(f"Connecting to MQTT broker {self.broker}:{self.port}...")
                self.client.connect_async(self.broker, self.port, keepalive=60)
                self.client.loop_start()
            except Exception as e:
                logger.warning(f"MQTT broker connection postponed: {e}")

        t = threading.Thread(target=_connect, daemon=True)
        t.start()

    def stop(self):
        """
        Gracefully terminates MQTT loop.
        """
        self._running = False
        self.client.loop_stop()
        self.client.disconnect()


# Singleton MQTT Subscriber Instance
mqtt_subscriber = MQTTSubscriber()
