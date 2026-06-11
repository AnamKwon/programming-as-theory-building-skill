from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class CreateSkuRequest(BaseModel):
    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    id: int
    status: str
    order_id: int


class CancelReservationResponse(BaseModel):
    id: int
    status: str
    stock_restored: int


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
