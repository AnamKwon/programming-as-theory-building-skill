from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class SKUTable(Base):
    __tablename__ = "skus"
    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    available_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ReservationTable(Base):
    __tablename__ = "reservations"
    id = Column(String(50), primary_key=True)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=ReservationStatus.PENDING)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FULFILLED = "fulfilled"


class OrderTable(Base):
    __tablename__ = "orders"
    id = Column(String(50), primary_key=True)
    reservation_id = Column(String(50), nullable=False)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=OrderStatus.PENDING)
    idempotency_key = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class SKUCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    available_stock: int = Field(default=0, ge=0)


class StockAdjustment(BaseModel):
    quantity_delta: int = Field(..., description="Positive or negative adjustment")


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    duration_minutes: int = Field(default=30, gt=0)


class ReservationConfirm(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationCancel(BaseModel):
    reason: str = Field(default="", max_length=255)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class SKUResponse(BaseModel):
    id: str
    name: str
    available_stock: int
    reserved_stock: int
    created_at: datetime


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    skip: int
    limit: int


class ErrorResponse(BaseModel):
    error: str
    detail: str


def get_engine(database_url: str = "sqlite:///commerce.db"):
    return create_engine(database_url, connect_args={"check_same_thread": False})


def get_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
