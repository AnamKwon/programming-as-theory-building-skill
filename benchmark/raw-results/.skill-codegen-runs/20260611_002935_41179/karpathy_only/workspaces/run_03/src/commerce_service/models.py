from pydantic import BaseModel, Field
from typing import Optional


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class AdjustStockRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    amount: int


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: str


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class StockAdjustResponse(BaseModel):
    sku: str
    stock: int


class HealthResponse(BaseModel):
    status: str
