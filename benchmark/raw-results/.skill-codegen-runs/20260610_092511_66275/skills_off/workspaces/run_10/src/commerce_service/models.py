from datetime import datetime
from enum import Enum
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, Session
from pydantic import BaseModel

Base = declarative_base()


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SKUModel(Base):
    __tablename__ = "skus"

    sku_id = Column(String, primary_key=True)
    stock_available = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(String, nullable=False, default=ReservationState.PENDING)
    idempotency_key = Column(String, nullable=True, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(String, nullable=False, default=ReservationState.CONFIRMED)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# Pydantic schemas
class SKUCreate(BaseModel):
    sku_id: str
    stock_available: int


class SKUResponse(BaseModel):
    sku_id: str
    stock_available: int
    created_at: datetime


class StockAdjustment(BaseModel):
    quantity_delta: int


class ReservationCreate(BaseModel):
    sku_id: str
    quantity: int
    idempotency_key: str | None = None


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    state: str
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    state: str
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int
