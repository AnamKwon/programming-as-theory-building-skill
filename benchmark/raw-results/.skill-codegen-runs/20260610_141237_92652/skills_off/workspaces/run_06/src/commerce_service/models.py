"""Data models for the commerce service."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Float, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# Pydantic request/response models
class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    idempotency_key: str
    status: ReservationStatus
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    size: int


class StockAdjustmentResponse(BaseModel):
    sku: str
    available_stock: int


# SQLAlchemy ORM models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False, index=True)
    initial_stock = Column(Integer, nullable=False)
    available_stock = Column(Integer, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, nullable=False, default=ReservationStatus.PENDING)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
