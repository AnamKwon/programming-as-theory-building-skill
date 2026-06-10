from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int
    created_at: datetime


class AdjustStockRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    amount: int


class AdjustStockResponse(BaseModel):
    sku: str
    available_stock: int


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    idempotency_key: str
    status: Literal["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]
    created_at: datetime
    updated_at: datetime


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
