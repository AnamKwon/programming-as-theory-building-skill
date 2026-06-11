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
    timestamp: datetime
    idempotency_key: str


class ConfirmReservationResponse(BaseModel):
    reservation_id: int
    order_id: int
    sku: str
    quantity: int
    timestamp: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    timestamp: datetime


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
