from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.orm import declarative_base
from pydantic import BaseModel, Field
from enum import Enum

Base = declarative_base()


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class ReservationStatus(str, Enum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# ORM Models

class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    available_stock = Column(Integer, nullable=False)
    reserved_stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.ACTIVE)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    order_id = Column(String, nullable=True)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.CONFIRMED)
    created_at = Column(DateTime, default=datetime.utcnow)


# Request/Response Models

class CreateSKURequest(BaseModel):
    id: str = Field(..., min_length=1)
    available_stock: int = Field(..., ge=0)


class CreateSKUResponse(BaseModel):
    id: str
    available_stock: int
    reserved_stock: int


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., description="Positive to increase, negative to decrease")


class AdjustStockResponse(BaseModel):
    id: str
    available_stock: int
    reserved_stock: int


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class CreateReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime


class ConfirmReservationRequest(BaseModel):
    pass


class ConfirmReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    order_id: str


class CancelReservationRequest(BaseModel):
    pass


class CancelReservationResponse(BaseModel):
    id: str
    status: ReservationStatus


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
