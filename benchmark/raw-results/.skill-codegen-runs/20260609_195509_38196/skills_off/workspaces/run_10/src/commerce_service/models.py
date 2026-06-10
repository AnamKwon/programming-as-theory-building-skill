from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SKUModel(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    stock_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    customer_id = Column(String, nullable=False, index=True)
    status = Column(String, default="pending", nullable=False)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    customer_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# Pydantic Schemas

class SKUCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    price: Decimal = Field(..., gt=0)
    stock_quantity: int = Field(default=0, ge=0)


class SKUResponse(BaseModel):
    id: int
    code: str
    price: Decimal
    stock_quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustment(BaseModel):
    quantity_delta: int = Field(..., description="Positive or negative quantity change")


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    customer_id: str = Field(..., min_length=1, max_length=100)
    ttl_seconds: int = Field(default=3600, ge=60)
    idempotency_key: str | None = Field(default=None, max_length=100)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    customer_id: str
    status: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    customer_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int


class HealthResponse(BaseModel):
    status: Literal["healthy"]
