from pydantic import BaseModel, Field
from typing import List, Optional


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
    idempotency_key: str
    status: str
    created_at: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: str


class PaginatedOrdersResponse(BaseModel):
    orders: List[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str


class StockResponse(BaseModel):
    sku: str
    available_stock: int
    reserved_stock: int
