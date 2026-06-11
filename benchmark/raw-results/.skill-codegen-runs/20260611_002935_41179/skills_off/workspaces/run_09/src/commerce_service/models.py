"""Pydantic models for request/response validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class CreateSKUResponse(BaseModel):
    sku: str
    stock: int


class StockAdjustRequest(BaseModel):
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
    created_at: datetime

    class Config:
        from_attributes = True


class ConfirmReservationResponse(BaseModel):
    reservation_id: int
    order_id: int
    status: str = "CONFIRMED"


class CancelReservationResponse(BaseModel):
    reservation_id: int
    status: str = "CANCELLED"
    stock_restored: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedOrdersResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int
