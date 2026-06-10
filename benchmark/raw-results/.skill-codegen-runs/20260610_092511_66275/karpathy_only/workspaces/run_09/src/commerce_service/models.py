"""SQLAlchemy ORM models and Pydantic schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SKUModel(Base):
    """SQLAlchemy ORM model for SKUs."""

    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    current_stock = Column(Integer, nullable=False, default=0)

    reservations = relationship("ReservationModel", back_populates="sku")


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ReservationModel(Base):
    """SQLAlchemy ORM model for reservations."""

    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default=ReservationStatus.PENDING)
    idempotency_key = Column(String, nullable=True, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    sku = relationship("SKUModel", back_populates="reservations")
    orders = relationship("OrderModel", back_populates="reservation")


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"


class OrderModel(Base):
    """SQLAlchemy ORM model for orders."""

    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, ForeignKey("reservations.id"), nullable=False)
    status = Column(String, nullable=False, default=OrderStatus.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    reservation = relationship("ReservationModel", back_populates="orders")


class SKURequest(BaseModel):
    """Request schema for creating a SKU."""

    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    """Response schema for SKU."""

    id: str
    name: str
    current_stock: int


class StockAdjustmentRequest(BaseModel):
    """Request schema for stock adjustment."""

    adjustment: int = Field(..., description="Positive or negative adjustment to stock")


class ReservationRequest(BaseModel):
    """Request schema for creating a reservation."""

    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(
        None, min_length=1, max_length=100, description="For idempotent retries"
    )
    ttl_seconds: int = Field(default=300, ge=30, description="Reservation expiration in seconds")


class ReservationResponse(BaseModel):
    """Response schema for reservation."""

    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    """Response schema for order."""

    id: str
    reservation_id: str
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    """Paginated response for orders."""

    orders: list[OrderResponse]
    cursor: Optional[str] = Field(None, description="Cursor for next page")
    has_more: bool = Field(default=False)
