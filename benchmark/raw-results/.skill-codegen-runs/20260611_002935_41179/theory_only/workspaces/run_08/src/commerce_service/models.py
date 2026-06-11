"""Pydantic models for request/response validation."""

from datetime import datetime
from pydantic import BaseModel, Field


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
    created_at: datetime
    idempotency_key: str

    class Config:
        from_attributes = True


class ConfirmReservationResponse(BaseModel):
    reservation_id: int
    order_id: int
    status: str


class CancelReservationResponse(BaseModel):
    reservation_id: int
    status: str
    restored_stock: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    size: int
    pages: int


class HealthResponse(BaseModel):
    status: str
