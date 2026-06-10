"""Data models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(100), unique=True, nullable=False, index=True)
    stock_available = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    reservations = relationship("ReservationModel", back_populates="sku")


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=ReservationStatus.PENDING)
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)

    sku = relationship("SKUModel", back_populates="reservations")
    orders = relationship("OrderModel", back_populates="reservation")


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=OrderStatus.PENDING)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    reservation = relationship("ReservationModel", back_populates="orders")


# Pydantic request/response models


class SKUCreate(BaseModel):
    sku_code: str
    stock_available: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    stock_available: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AdjustStockRequest(BaseModel):
    quantity_delta: int


class ReservationRequest(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    idempotency_key: str
    ttl_seconds: int = Field(default=300, gt=0)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class OrderConfirmRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int
