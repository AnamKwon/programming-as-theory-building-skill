from datetime import datetime
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class StockAdjust(BaseModel):
    sku: str
    amount: int


class ReservationCreate(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: str


class OrderList(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
