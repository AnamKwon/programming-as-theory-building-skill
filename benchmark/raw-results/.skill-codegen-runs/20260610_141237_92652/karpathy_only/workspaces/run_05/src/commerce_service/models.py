from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

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
    created_at: float

class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: float

class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    size: int
