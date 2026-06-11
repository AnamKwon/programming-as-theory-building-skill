"""Pydantic models for request/response validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int = Field(gt=0)


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
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
    status: str
    confirmed_at: datetime


class CancelReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


class OrderResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
