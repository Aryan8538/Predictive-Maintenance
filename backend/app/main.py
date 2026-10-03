"""
FastAPI Application Entrypoint for AI-Based Predictive Maintenance System.
Provides REST APIs, WebSocket streaming, and orchestrates the MQTT background ingestion.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .db import init_db, get_db
from .models import (
    SensorReading,
    Prediction,
    LatestReadingsResponse,
    ReadingHistoryItem,
    PredictionResult,
    PredictionHistoryItem
)
from .inference import inference_engine
from .mqtt_subscriber import mqtt_subscriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("predictive_maintenance.api")


# ==========================================
# WebSocket Connection Manager
# ==========================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    def broadcast_sync(self, message: dict):
        """
        Thread-safe broadcast called from MQTT background thread.
        Schedules broadcast on the active asyncio event loop.
        """
        if self.loop and self.active_connections:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket client: {e}")
                self.disconnect(connection)


ws_manager = ConnectionManager()


# ==========================================
# Lifespan Lifecycle
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Database schema...")
    init_db()

    logger.info("Connecting MQTT Subscriber...")
    ws_manager.loop = asyncio.get_running_loop()
    mqtt_subscriber.set_broadcast_callback(ws_manager.broadcast_sync)
    mqtt_subscriber.start()

    yield

    logger.info("Shutting down MQTT Subscriber...")
    mqtt_subscriber.stop()


app = FastAPI(
    title="AI-Based Predictive Maintenance API",
    description="Real-time condition monitoring, vibration analytics, and fault prediction system.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration to allow local Vite React dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# REST API Endpoints
# ==========================================

@app.get("/health")
def health_check():
    """System health check and broker connectivity status."""
    return {
        "status": "online",
        "mqtt_connected": mqtt_subscriber.client.is_connected(),
        "model_loaded": inference_engine.model is not None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/readings/latest", response_model=LatestReadingsResponse)
def get_latest_readings(db: Session = Depends(get_db)):
    """
    Returns the most recent vibration and temperature readings.
    """
    vib = mqtt_subscriber.latest_vibration
    temp = mqtt_subscriber.latest_temperature

    # Fallback to querying DB if subscriber memory cache is empty
    if not vib:
        last_vib_row = (
            db.query(SensorReading)
            .filter(SensorReading.reading_type == "vibration")
            .order_by(desc(SensorReading.recorded_at))
            .first()
        )
        if last_vib_row:
            vib = {
                "x": last_vib_row.x,
                "y": last_vib_row.y,
                "z": last_vib_row.z,
                "timestamp": int(last_vib_row.recorded_at.timestamp() * 1000)
            }

    if not temp:
        last_temp_row = (
            db.query(SensorReading)
            .filter(SensorReading.reading_type == "temperature")
            .order_by(desc(SensorReading.recorded_at))
            .first()
        )
        if last_temp_row:
            temp = {
                "temp": last_temp_row.temp,
                "timestamp": int(last_temp_row.recorded_at.timestamp() * 1000)
            }

    latest_pred = inference_engine.get_latest()
    rms_val = latest_pred.get("rms", None)

    return LatestReadingsResponse(
        vibration=vib,
        temperature=temp,
        rms=rms_val
    )


@app.get("/api/readings/history", response_model=List[ReadingHistoryItem])
def get_readings_history(
    minutes: int = Query(default=10, ge=1, le=1440),
    db: Session = Depends(get_db)
):
    """
    Returns time series telemetry for historical charts within the specified past minutes.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    readings = (
        db.query(SensorReading)
        .filter(SensorReading.recorded_at >= cutoff)
        .order_by(SensorReading.recorded_at.asc())
        .limit(1000)
        .all()
    )
    return readings


@app.get("/api/predictions/latest", response_model=PredictionResult)
def get_latest_prediction():
    """
    Returns the current health status, confidence score, and RMS.
    """
    return inference_engine.get_latest()


@app.get("/api/predictions/history", response_model=List[PredictionHistoryItem])
def get_predictions_history(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Returns historical log of state changes, warnings, and alerts.
    """
    alerts = (
        db.query(Prediction)
        .order_by(desc(Prediction.predicted_at))
        .limit(limit)
        .all()
    )
    return alerts


# ==========================================
# WebSocket Streaming Endpoint
# ==========================================

@app.websocket("/api/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    """
    Real-time push channel delivering live vibration, temperature, and predictions
    as they are processed by the backend.
    """
    await ws_manager.connect(websocket)
    try:
        # Send immediate initial state upon connection
        init_payload = {
            "type": "initial_state",
            "vibration": mqtt_subscriber.latest_vibration,
            "temperature": mqtt_subscriber.latest_temperature,
            "prediction": inference_engine.get_latest()
        }
        await websocket.send_json(init_payload)

        # Keep connection open and receive any client ping
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
        ws_manager.disconnect(websocket)
