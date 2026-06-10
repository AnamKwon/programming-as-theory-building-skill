"""Data models for requests, responses, and database persistence."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# SQLAlchemy ORM models
class SkuModel(Base):
    __tablename__ = "skus"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class StockModel(Base):
    __tablename__ = "stock"
    sku_id = Column(String, primary_key=True)
    quantity = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"
    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending")
    idempotency_key = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="confirmed")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Pydantic request/response models
class SkuRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)


class SkuResponse(BaseModel):
    id: str
    name: str
    created_at: datetime


class StockAdjustmentRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    delta: int = Field(..., description="Amount to adjust (positive or negative)")


class ReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, description="Unique key for idempotency")
    ttl_seconds: int = Field(default=300, ge=60, le=3600, description="Reservation TTL in seconds")


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
    code: str
