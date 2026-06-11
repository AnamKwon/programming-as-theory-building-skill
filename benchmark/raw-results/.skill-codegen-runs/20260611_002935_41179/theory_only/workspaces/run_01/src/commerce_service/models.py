"""Data models for the commerce service."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    stock: int


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    new_stock: int


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


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
