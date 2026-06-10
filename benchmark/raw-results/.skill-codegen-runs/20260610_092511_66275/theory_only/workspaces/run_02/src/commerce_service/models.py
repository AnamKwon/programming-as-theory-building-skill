from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    CONFIRMED = "confirmed"
    COMPLETED = "completed"


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class StockModel(Base):
    __tablename__ = "stock"

    sku_id = Column(String, ForeignKey("skus.id"), primary_key=True)
    quantity_available = Column(Integer, default=0, nullable=False)
    quantity_reserved = Column(Integer, default=0, nullable=False)
    version = Column(Integer, default=1, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, ForeignKey("reservations.id"), nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.CONFIRMED, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class SKURequest(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str | None = None


class SKUResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjustRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity_delta: int = Field(...)


class ReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str | None = None


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    status: OrderStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int
