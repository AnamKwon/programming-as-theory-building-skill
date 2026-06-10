from pydantic import BaseModel, Field
from datetime import datetime
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


class ConfirmReservationRequest(BaseModel):
    pass


class CancelReservationRequest(BaseModel):
    pass


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


class HealthResponse(BaseModel):
    status: str
