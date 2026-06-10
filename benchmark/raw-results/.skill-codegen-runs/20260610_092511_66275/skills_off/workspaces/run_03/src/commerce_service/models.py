"""Data models for commerce service."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SKUModel(Base):
    """SKU (stock-keeping unit) database model."""

    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ReservationModel(Base):
    """Reservation database model."""

    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class OrderModel(Base):
    """Order database model."""

    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False, unique=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# Pydantic schemas for API requests/responses


class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: str
    name: str
    stock: int
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    delta: int = Field(..., ne=0)


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime
    confirmed_at: datetime | None = None

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
