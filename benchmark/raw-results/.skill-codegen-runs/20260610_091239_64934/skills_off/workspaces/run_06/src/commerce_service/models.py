from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import declarative_base

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

    id = Column(Integer, primary_key=True)
    sku_code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    stock_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=ReservationStatus.PENDING, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    status = Column(String, default=OrderStatus.PENDING, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OrderReservation(Base):
    __tablename__ = "order_reservations"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, nullable=False, index=True)
    reservation_id = Column(Integer, nullable=False, index=True)


# Pydantic Request/Response Models
class SKUCreate(BaseModel):
    sku_code: str
    name: str
    stock_quantity: int = Field(ge=0)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str
    stock_quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustment(BaseModel):
    adjustment: int


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    idempotency_key: Optional[str] = None


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
