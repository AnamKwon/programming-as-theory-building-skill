"""Database models and Pydantic schemas."""

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


# SQLAlchemy Models


class SKU(Base):
    __tablename__ = "skus"

    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    inventory = relationship("Inventory", back_populates="sku", uselist=False, cascade="all, delete-orphan")
    reservations = relationship("Reservation", back_populates="sku", cascade="all, delete-orphan")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    sku_id = Column(String(50), ForeignKey("skus.id"), nullable=False, unique=True)
    available_quantity = Column(Float, default=0, nullable=False)
    reserved_quantity = Column(Float, default=0, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    sku = relationship("SKU", back_populates="inventory")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String(50), primary_key=True)
    sku_id = Column(String(50), ForeignKey("skus.id"), nullable=False)
    order_id = Column(String(50), ForeignKey("orders.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(String(20), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    sku = relationship("SKU", back_populates="reservations")
    order = relationship("Order", back_populates="reservations")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(50), primary_key=True)
    status = Column(String(20), default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    reservations = relationship("Reservation", back_populates="order", cascade="all, delete-orphan")


# Pydantic Schemas


class SKUCreate(BaseModel):
    id: str
    name: str


class SKUResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InventoryResponse(BaseModel):
    sku_id: str
    available_quantity: float
    reserved_quantity: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReservationCreate(BaseModel):
    sku_id: str
    order_id: str
    quantity: float
    idempotency_key: Optional[str] = None
    ttl_seconds: int = 3600


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    order_id: str
    quantity: float
    status: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjust(BaseModel):
    quantity_change: float


class OrderResponse(BaseModel):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    reservations: list[ReservationResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
