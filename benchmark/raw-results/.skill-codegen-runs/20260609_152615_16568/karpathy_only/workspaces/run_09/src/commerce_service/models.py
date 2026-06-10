from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


# Request/Response Models


class CreateSKURequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class SKUResponse(BaseModel):
    sku_code: str
    description: Optional[str]
    created_at: datetime


class AdjustStockRequest(BaseModel):
    quantity_delta: int = Field(..., description="Positive or negative quantity change")


class CreateReservationRequest(BaseModel):
    sku_code: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=256)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_code: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime
    confirmed_at: Optional[datetime] = None


class OrderResponse(BaseModel):
    order_id: str
    sku_code: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrdersListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


# ORM Models


class SKU(Base):
    __tablename__ = "skus"

    sku_code = Column(String(100), primary_key=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Stock(Base):
    __tablename__ = "stocks"

    sku_code = Column(String(100), primary_key=True)
    quantity = Column(Integer, default=0)
    reserved_quantity = Column(Integer, default=0)
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (UniqueConstraint("sku_code", "idempotency_key", name="uq_sku_idempotency"),)

    reservation_id = Column(String(36), primary_key=True)
    sku_code = Column(String(100))
    quantity = Column(Integer)
    idempotency_key = Column(String(256))
    status = Column(String(50), default=ReservationStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True))
    confirmed_at = Column(DateTime(timezone=True), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String(36), primary_key=True)
    sku_code = Column(String(100))
    quantity = Column(Integer)
    status = Column(String(50), default=OrderStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_from_reservation_id = Column(String(36), nullable=True)


def get_engine(database_url: str = "sqlite:///./commerce_service.db"):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
