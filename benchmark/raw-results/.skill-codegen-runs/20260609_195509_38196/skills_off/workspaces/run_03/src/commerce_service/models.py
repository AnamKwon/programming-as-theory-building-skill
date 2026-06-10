from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    stock = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    state = Column(String, default=ReservationState.PENDING.value, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False)
    sku_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    state = Column(String, default=OrderState.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# Request/Response schemas

class CreateSKURequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: int
    name: str
    stock: int
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    quantity_delta: int = Field(..., description="Change in quantity (can be negative)")


class CreateReservationRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    state: ReservationState
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: int
    state: OrderState
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: Optional[int] = None


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
