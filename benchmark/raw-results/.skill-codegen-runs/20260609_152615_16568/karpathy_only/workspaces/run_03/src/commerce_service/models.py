from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SKUOrmModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    available_stock = Column(Integer, default=0, nullable=False)
    reserved_stock = Column(Integer, default=0, nullable=False)


class ReservationOrmModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class OrderOrmModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class SKUCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: int
    code: str
    name: str
    available_stock: int
    reserved_stock: int

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity_change: int = Field(..., ne=0)


class ReservationCreateRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, gt=0)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: Literal["pending", "confirmed", "cancelled"]
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[OrderResponse]
