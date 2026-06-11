"""Pydantic models for request/response validation."""

from datetime import datetime
from pydantic import BaseModel, Field


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
    created_at: datetime
    idempotency_key: str


class ConfirmReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    order_id: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
