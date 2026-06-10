"""Pydantic models and database schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    available_stock: int
    reserved_stock: int


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int
    reserved_stock: int


class ReservationCreate(BaseModel):
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


class ReservationConfirmResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    order_id: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
