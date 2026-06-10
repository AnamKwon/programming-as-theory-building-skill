"""Data models for requests, responses, and ORM."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ORM Models
class SKUModel(Base):
    """Product inventory unit."""

    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(100), unique=True, nullable=False, index=True)
    qty_on_hand = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    reservations = relationship("ReservationModel", back_populates="sku", cascade="all, delete-orphan")
    orders = relationship("OrderModel", back_populates="sku", cascade="all, delete-orphan")


class ReservationModel(Base):
    """Temporary inventory hold."""

    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    status = Column(
        Enum("pending", "confirmed", "cancelled", name="reservation_status"),
        nullable=False,
        default="pending",
    )
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    sku = relationship("SKUModel", back_populates="reservations")
    order = relationship("OrderModel", back_populates="reservation", uselist=False)


class OrderModel(Base):
    """Confirmed order from a reservation."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, unique=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    status = Column(
        Enum("confirmed", "shipped", "cancelled", name="order_status"),
        nullable=False,
        default="confirmed",
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    reservation = relationship("ReservationModel", back_populates="order")
    sku = relationship("SKUModel", back_populates="orders")


# Pydantic Request/Response Models
class SKUCreate(BaseModel):
    """Request to create a SKU."""

    sku_code: str = Field(..., min_length=1, max_length=100)
    qty: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    """Response with SKU details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku_code: str
    qty_on_hand: int
    created_at: datetime
    updated_at: datetime


class StockAdjustment(BaseModel):
    """Request to adjust stock."""

    delta: int = Field(..., ge=-9999, le=9999)


class ReservationCreate(BaseModel):
    """Request to create a reservation."""

    sku_id: int = Field(..., gt=0)
    qty: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class ReservationResponse(BaseModel):
    """Response with reservation details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku_id: int
    qty: int
    status: Literal["pending", "confirmed", "cancelled"]
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    """Response with order details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reservation_id: int
    sku_id: int
    qty: int
    status: Literal["confirmed", "shipped", "cancelled"]
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    """Paginated list of orders."""

    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int
