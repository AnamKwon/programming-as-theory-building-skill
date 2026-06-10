from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SkuCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0)


class SkuResponse(BaseModel):
    sku_id: str
    name: str
    price: float
    current_stock: int


class StockAdjustment(BaseModel):
    quantity: int = Field(..., description="Quantity to add (can be negative)")


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    expires_at: datetime
    idempotency_key: str


class ReservationConfirm(BaseModel):
    pass


class OrderItem(BaseModel):
    sku_id: str
    quantity: int
    price: float


class OrderResponse(BaseModel):
    order_id: str
    status: str
    items: list[OrderItem]
    created_at: datetime


class OrdersListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    skip: int
    limit: int


class HealthResponse(BaseModel):
    status: str
    database: str


class ErrorResponse(BaseModel):
    detail: str
