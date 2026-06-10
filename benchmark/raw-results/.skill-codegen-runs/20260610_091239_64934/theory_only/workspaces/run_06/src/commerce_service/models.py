from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku: str
    name: str
    available_stock: int
    reserved_stock: int
    total_stock: int


class AdjustStockRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., ne=0)


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class ConfirmReservationRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    order_id: str
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str


class SKU(Base):
    __tablename__ = "skus"
    sku = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    total_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)


class Reservation(Base):
    __tablename__ = "reservations"
    reservation_id = Column(String(36), primary_key=True)
    sku = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String(255), nullable=True, unique=True)


class Order(Base):
    __tablename__ = "orders"
    order_id = Column(String(36), primary_key=True)
    sku = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    reservation_id = Column(String(36), nullable=False)


def init_db(db_url: str = "sqlite:///commerce.db"):
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine
