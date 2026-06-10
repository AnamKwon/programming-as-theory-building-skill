from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# Pydantic request/response models
class CreateSkuRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    stock: int = Field(..., gt=0)


class SkuResponse(BaseModel):
    id: int
    sku: str
    stock: int
    reserved: int
    available: int
    created_at: datetime

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., ne=0)


class CreateReservationRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=128)


class ReservationResponse(BaseModel):
    id: int
    order_id: str
    sku_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ConfirmReservationRequest(BaseModel):
    pass


class CancelReservationRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    order_id: str
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    status: str
    version: str


# SQLAlchemy ORM models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String(64), unique=True, nullable=False, index=True)
    stock = Column(Integer, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    @property
    def available(self) -> int:
        return max(0, self.stock - self.reserved)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    order_id = Column(String(36), unique=True, nullable=False, index=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(16), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String(128), index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
