from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class SKUCreate(BaseModel):
    sku_code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    stock_count: int = Field(default=0, ge=0)


class SKU(SKUCreate):
    id: int


class StockAdjustment(BaseModel):
    sku_id: int
    quantity_delta: int


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    state: Literal["pending", "confirmed", "cancelled"]
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    state: Literal["reserved", "confirmed", "completed", "cancelled"]
    created_at: datetime


class OrderList(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str
