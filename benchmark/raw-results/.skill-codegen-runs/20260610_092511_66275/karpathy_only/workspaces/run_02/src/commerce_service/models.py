from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderState(str, Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SKUorm(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True, index=True)
    sku_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)


class ReservationORM(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    state = Column(String, nullable=False, default=ReservationState.PENDING)
    created_at = Column(DateTime, nullable=False, default=func.now())


class OrderORM(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    state = Column(String, nullable=False, default=OrderState.CONFIRMED)
    created_at = Column(DateTime, nullable=False, default=func.now())


class SKUSchema(BaseModel):
    id: int
    sku_code: str
    name: str
    quantity: int

    class Config:
        from_attributes = True


class SKUCreateRequest(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(default=0, ge=0)


class StockAdjustmentRequest(BaseModel):
    quantity_delta: int = Field(..., description="Positive or negative quantity change")


class ReservationSchema(BaseModel):
    id: int
    sku_id: int
    quantity: int
    state: str
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ReservationCreateRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: Optional[str] = Field(None, max_length=255)


class OrderSchema(BaseModel):
    id: int
    reservation_id: int
    state: str
    created_at: datetime

    class Config:
        from_attributes = True
