"""Pydantic models for request/response validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int = Field(gt=0)


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: Literal["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: Literal["CONFIRMED"]
    order_id: int


class CancelReservationResponse(BaseModel):
    id: int
    status: Literal["CANCELLED"]
    restored_stock: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    size: int


class StockAdjustResponse(BaseModel):
    sku: str
    previous_stock: int
    new_stock: int
    adjustment: int
