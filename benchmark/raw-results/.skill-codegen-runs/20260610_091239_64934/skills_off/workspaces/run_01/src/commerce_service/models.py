from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


# Database Models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    available_stock = Column(Integer, default=0)
    reserved_stock = Column(Integer, default=0)

    reservations = relationship("Reservation", back_populates="sku")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String(36), primary_key=True)
    sku_id = Column(String(50), ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(SQLEnum(ReservationState), default=ReservationState.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String(255), nullable=True, unique=True)

    sku = relationship("SKU", back_populates="reservations")
    order_items = relationship("OrderItem", back_populates="reservation")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True)
    state = Column(SQLEnum(OrderState), default=OrderState.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)
    reservation_id = Column(String(36), ForeignKey("reservations.id"), nullable=False)

    order = relationship("Order", back_populates="order_items")
    reservation = relationship("Reservation", back_populates="order_items")


# Pydantic Models
class SKUCreate(BaseModel):
    name: str
    quantity: int = Field(gt=0, description="Initial stock quantity")


class SKUResponse(BaseModel):
    id: str
    name: str
    available_stock: int
    reserved_stock: int


class AdjustStockRequest(BaseModel):
    quantity: int = Field(description="Positive to add, negative to subtract")


class ReservationRequest(BaseModel):
    sku_id: str
    quantity: int = Field(gt=0)
    idempotency_key: str = Field(description="Unique key for idempotency")


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderItemResponse(BaseModel):
    reservation_id: str
    quantity: int


class OrderResponse(BaseModel):
    id: str
    state: OrderState
    items: list[OrderItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    size: int


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
