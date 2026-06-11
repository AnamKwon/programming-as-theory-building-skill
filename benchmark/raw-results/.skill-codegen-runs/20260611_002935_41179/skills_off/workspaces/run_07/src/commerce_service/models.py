"""Data models for the commerce service."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    available_stock: int


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    size: int
    total_pages: int


class ErrorResponse(BaseModel):
    detail: str
