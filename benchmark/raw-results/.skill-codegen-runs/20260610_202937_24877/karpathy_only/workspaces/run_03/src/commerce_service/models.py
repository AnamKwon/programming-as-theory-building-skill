from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class CreateSKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int
    created_at: datetime


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
    status: str
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class ConfirmReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime


class CancelReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
