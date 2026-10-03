"""
SQLAlchemy Models and Pydantic Schemas.
Implements the exact PostgreSQL schema defined in Section 4 of the spec.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, Float, String, DateTime, func
from pydantic import BaseModel, ConfigDict
from .db import Base


# ==========================================
# SQLAlchemy ORM Models
# ==========================================

class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    reading_type = Column(String(20), nullable=False)  # 'vibration' or 'temperature'
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    z = Column(Float, nullable=True)
    temp = Column(Float, nullable=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    status = Column(String(10), nullable=False)  # 'Healthy' | 'Warning' | 'Critical'
    confidence = Column(Float, nullable=False)
    rms = Column(Float, nullable=True)
    predicted_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ==========================================
# Pydantic Schemas for API & Validation
# ==========================================

class VibrationData(BaseModel):
    x: float
    y: float
    z: float
    timestamp: int  # Epoch ms


class TemperatureData(BaseModel):
    temp: float
    timestamp: int  # Epoch ms


class PredictionResult(BaseModel):
    status: str  # "Healthy" | "Warning" | "Critical"
    confidence: float
    rms: Optional[float] = None
    predicted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class LatestReadingsResponse(BaseModel):
    vibration: Optional[VibrationData] = None
    temperature: Optional[TemperatureData] = None
    rms: Optional[float] = None


class ReadingHistoryItem(BaseModel):
    id: int
    reading_type: str
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    temp: Optional[float] = None
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PredictionHistoryItem(BaseModel):
    id: int
    status: str
    confidence: float
    rms: Optional[float] = None
    predicted_at: datetime

    model_config = ConfigDict(from_attributes=True)
