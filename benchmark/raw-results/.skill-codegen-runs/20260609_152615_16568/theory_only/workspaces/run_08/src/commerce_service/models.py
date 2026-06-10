from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUOrm(Base):
    __tablename__ = "skus"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    stock_quantity = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReservationOrm(Base):
    __tablename__ = "reservations"
    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=ReservationStatus.PENDING)
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class OrderOrm(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False, unique=True)
    status = Column(String, default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)


class SKURequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: str
    name: str
    stock_quantity: int
    created_at: datetime


class StockAdjustmentRequest(BaseModel):
    adjustment: int = Field(..., description="Positive to add, negative to remove")


class ReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


def get_engine():
    engine = create_engine("sqlite:///./commerce.db")
    Base.metadata.create_all(engine)
    return engine
