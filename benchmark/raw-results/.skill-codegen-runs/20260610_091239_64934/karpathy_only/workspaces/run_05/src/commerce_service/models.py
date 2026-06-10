from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    CREATED = "created"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"

    sku_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    total_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=func.now())


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.sku_id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True)
    reservation_id = Column(String, ForeignKey("reservations.reservation_id"), nullable=False)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.CREATED)
    created_at = Column(DateTime, nullable=False, default=func.now())


class SKUCreateRequest(BaseModel):
    sku_id: str
    name: str
    total_stock: int = Field(ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    total_stock: int
    reserved_stock: int
    available_stock: int

    model_config = {"from_attributes": True}


class StockAdjustmentRequest(BaseModel):
    adjustment: int


class ReservationCreateRequest(BaseModel):
    sku_id: str
    quantity: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime
    confirmed_at: datetime | None = None

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    status: OrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str
