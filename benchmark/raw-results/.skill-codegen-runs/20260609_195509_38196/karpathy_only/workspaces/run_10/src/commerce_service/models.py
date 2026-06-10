from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

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


# SQLAlchemy models
class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku_code = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InventoryModel(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, index=True, nullable=False)
    available_quantity = Column(Integer, default=0, nullable=False)
    reserved_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, index=True, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING)
    idempotency_key = Column(String(255), index=True, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, index=True, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    reservation_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Pydantic models
class SKUCreate(BaseModel):
    sku_code: str
    name: str


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjustment(BaseModel):
    sku_id: int
    quantity_delta: int


class InventoryResponse(BaseModel):
    id: int
    sku_id: int
    available_quantity: int
    reserved_quantity: int

    model_config = {"from_attributes": True}


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int
    idempotency_key: str = Field(description="Unique key for idempotent requests")
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, description="Reservation TTL in seconds")


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    orders: list[OrderResponse]


class ErrorResponse(BaseModel):
    detail: str
