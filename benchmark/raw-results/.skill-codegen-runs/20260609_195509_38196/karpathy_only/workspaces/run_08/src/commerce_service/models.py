from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SQLEnum
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


# SQLAlchemy Models
class SKUModel(Base):
    __tablename__ = "skus"

    sku_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(256), nullable=False)
    available_stock = Column(Integer, default=0, nullable=False)
    reserved_stock = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String(64), primary_key=True, index=True)
    sku_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String(128), unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String(64), primary_key=True, index=True)
    reservation_id = Column(String(64), nullable=False, index=True)
    sku_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Pydantic Request/Response Models
class SKUCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=256)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    available_stock: int
    reserved_stock: int
    created_at: datetime

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    adjustment: int = Field(..., description="Positive or negative adjustment")


class ReservationCreateRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=64)
    customer_id: str = Field(..., min_length=1, max_length=64)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, max_length=128)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    customer_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ReservationConfirmRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    customer_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    detail: str
    code: str
    timestamp: datetime
