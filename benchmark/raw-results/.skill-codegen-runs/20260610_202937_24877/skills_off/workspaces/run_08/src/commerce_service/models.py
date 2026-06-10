from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SKUCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class StockAdjustRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


class ReservationCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    detail: str
