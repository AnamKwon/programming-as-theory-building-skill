from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Enum as SQLEnum, ForeignKey, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# Pydantic request/response models
class SKUCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    code: str
    name: str
    available_stock: int

    class Config:
        from_attributes = True


class StockAdjustment(BaseModel):
    amount: int = Field(..., description="Positive to add, negative to remove")


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ReservationCreate(BaseModel):
    sku_id: int
    amount: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    amount: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ReservationConfirm(BaseModel):
    pass


class ReservationCancel(BaseModel):
    pass


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    amount: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# SQLAlchemy ORM models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    available_stock = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    idempotency_key = Column(String(100), nullable=False, index=True)
    status = Column(SQLEnum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
