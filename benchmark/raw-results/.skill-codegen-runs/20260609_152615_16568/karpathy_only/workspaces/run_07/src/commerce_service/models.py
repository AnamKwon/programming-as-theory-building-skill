from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
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


class SKU(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    available_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)

    reservations = relationship("Reservation", back_populates="sku")
    order_items = relationship("OrderItem", back_populates="sku")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    sku = relationship("SKU", back_populates="reservations")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default=OrderStatus.PENDING)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
    sku = relationship("SKU", back_populates="order_items")


class SKUCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    available_stock: int
    reserved_stock: int

    model_config = {"from_attributes": True}


class AdjustStockRequest(BaseModel):
    quantity: int = Field(...)


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class OrderItemResponse(BaseModel):
    sku_id: str
    quantity: int

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    order_id: str
    status: str
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    pages: int


class HealthResponse(BaseModel):
    status: str
