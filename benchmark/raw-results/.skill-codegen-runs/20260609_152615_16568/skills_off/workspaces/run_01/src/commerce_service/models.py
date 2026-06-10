from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# SQLAlchemy ORM models


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    stock = relationship("StockModel", back_populates="sku", uselist=False)
    reservations = relationship("ReservationModel", back_populates="sku")


class StockModel(Base):
    __tablename__ = "stock"

    sku_id = Column(String, ForeignKey("skus.id"), primary_key=True)
    quantity = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    sku = relationship("SKUModel", back_populates="stock")


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)

    sku = relationship("SKUModel", back_populates="reservations")
    order_reservations = relationship("OrderReservationModel", back_populates="reservation")


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    status = Column(String, default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    confirmed_at = Column(DateTime, nullable=True)

    order_reservations = relationship("OrderReservationModel", back_populates="order")


class OrderReservationModel(Base):
    __tablename__ = "order_reservations"

    order_id = Column(String, ForeignKey("orders.id"), primary_key=True)
    reservation_id = Column(String, ForeignKey("reservations.id"), primary_key=True)

    order = relationship("OrderModel", back_populates="order_reservations")
    reservation = relationship("ReservationModel", back_populates="order_reservations")


# Pydantic request/response models


class CreateSKURequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class SKUResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime


class AdjustStockRequest(BaseModel):
    quantity: int = Field(..., ge=-1_000_000, le=1_000_000)


class StockResponse(BaseModel):
    sku_id: str
    quantity: int
    updated_at: datetime


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0, le=1_000_000)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    reservation_ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime
    expires_at: datetime
    confirmed_at: Optional[datetime] = None


class OrderResponse(BaseModel):
    id: str
    status: str
    reservations: list[ReservationResponse]
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class HealthResponse(BaseModel):
    status: str
