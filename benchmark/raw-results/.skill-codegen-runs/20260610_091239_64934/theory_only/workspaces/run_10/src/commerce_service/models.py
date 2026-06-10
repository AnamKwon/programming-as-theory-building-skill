from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(String, primary_key=True)
    total_stock = Column(Integer, nullable=False)
    reserved_stock = Column(Integer, default=0, nullable=False)
    sold_stock = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    @property
    def available_stock(self) -> int:
        return self.total_stock - self.reserved_stock - self.sold_stock


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="active", nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    sku_id = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default=OrderStatus.PENDING.value, nullable=False)
    reservation_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)


# Request/Response Models

class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    stock: int = Field(..., gt=0)


class SKUResponse(BaseModel):
    sku_id: str
    total_stock: int
    available_stock: int
    reserved_stock: int
    sold_stock: int


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., description="Change in stock level (positive or negative)")


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = None


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    expires_at: datetime


class ConfirmReservationRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str
