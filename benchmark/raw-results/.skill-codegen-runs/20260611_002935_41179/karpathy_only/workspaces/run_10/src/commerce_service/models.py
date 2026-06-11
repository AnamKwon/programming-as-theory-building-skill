"""Pydantic models for request/response validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    available_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class AdjustStockResponse(BaseModel):
    sku: str
    available_stock: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: ReservationStatus
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: ReservationStatus
    order_id: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrdersListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class ErrorResponse(BaseModel):
    detail: str
