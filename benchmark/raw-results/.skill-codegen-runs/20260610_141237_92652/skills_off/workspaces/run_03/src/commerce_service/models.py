"""Pydantic models for request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SKUCreateRequest(BaseModel):
    sku: str
    initial_stock: int


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class ReservationCreateRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    idempotency_key: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class PaginatedOrders(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    detail: str
