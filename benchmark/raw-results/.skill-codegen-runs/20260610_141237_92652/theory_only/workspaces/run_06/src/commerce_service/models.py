from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    stock: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: Literal["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]
    idempotency_key: str
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: Literal["CONFIRMED"]
    created_at: datetime
    order_id: int


class CancelReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: Literal["CANCELLED"]
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    created_at: datetime
    reservation_id: int


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
