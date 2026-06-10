from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    sku_id: str
    name: str

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    quantity: int = Field(..., description="Change in stock quantity (positive or negative)")


class StockResponse(BaseModel):
    sku_id: str
    available: int
    reserved: int
    total: int

    class Config:
        from_attributes = True


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class SKUModel(Base):
    __tablename__ = "skus"

    sku_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    available = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String(36), primary_key=True)
    sku_id = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(SQLEnum(ReservationStatus), default=ReservationStatus.PENDING, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    order_id = Column(String(36), primary_key=True)
    reservation_id = Column(String(36), nullable=False, unique=True, index=True)
    sku_id = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
