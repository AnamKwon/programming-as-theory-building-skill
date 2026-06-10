from datetime import datetime
from pydantic import BaseModel


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    status: str
    created_at: str


class OrderResponse(BaseModel):
    id: str
    reservation_id: str
    created_at: str


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    page: int
    size: int
    total: int
