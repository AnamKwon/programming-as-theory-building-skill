from pydantic import BaseModel
from datetime import datetime


class SKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime


class ConfirmReservationResponse(BaseModel):
    reservation_id: int
    order_id: int
    status: str


class CancelReservationResponse(BaseModel):
    reservation_id: int
    status: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
