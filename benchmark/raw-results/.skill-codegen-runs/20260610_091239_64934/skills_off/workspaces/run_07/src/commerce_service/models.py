"""Data models for commerce service."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKU(Base):
    """Product SKU."""

    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Stock(Base):
    """Inventory stock for a SKU."""

    __tablename__ = "stock"

    sku_id = Column(String, primary_key=True)
    quantity = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, onupdate=func.now(), server_default=func.now())


class Reservation(Base):
    """Reservation for inventory."""

    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default=OrderStatus.RESERVED.value)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class CreateSKURequest(BaseModel):
    """Request to create a SKU."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class SKUResponse(BaseModel):
    """Response with SKU details."""

    id: str
    name: str
    created_at: datetime


class AdjustStockRequest(BaseModel):
    """Request to adjust stock."""

    sku_id: str = Field(..., min_length=1)
    delta: int = Field(..., description="Positive or negative adjustment")


class StockResponse(BaseModel):
    """Response with stock details."""

    sku_id: str
    quantity: int


class CreateReservationRequest(BaseModel):
    """Request to create a reservation."""

    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)
    ttl_seconds: int = Field(default=300, ge=1)


class ReservationResponse(BaseModel):
    """Response with reservation details."""

    id: str
    sku_id: str
    quantity: int
    status: str
    expires_at: datetime
    created_at: datetime


class ConfirmReservationRequest(BaseModel):
    """Request to confirm a reservation."""

    idempotency_key: str = Field(..., min_length=1)


class CancelReservationRequest(BaseModel):
    """Request to cancel a reservation."""

    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    """Response with order details."""

    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class OrdersListResponse(BaseModel):
    """Response with paginated orders."""

    items: list[OrderResponse]
    total: int
    skip: int
    limit: int


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
