from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


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
    status: str
    created_at: str


class ConfirmReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    order_id: int


class CancelReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    restored_stock: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: str


class OrdersListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
