from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: str
    idempotency_key: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: str


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


class ErrorResponse(BaseModel):
    detail: str
