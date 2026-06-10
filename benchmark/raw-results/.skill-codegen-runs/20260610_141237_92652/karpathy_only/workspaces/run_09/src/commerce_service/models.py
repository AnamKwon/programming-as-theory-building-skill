from datetime import datetime
from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    available_stock: int
    reserved_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustmentResponse(BaseModel):
    sku: str
    available_stock: int
    reserved_stock: int


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


class ConfirmReservationResponse(BaseModel):
    reservation_id: int
    order_id: int
    sku: str
    quantity: int
    status: str


class CancelReservationResponse(BaseModel):
    reservation_id: int
    sku: str
    quantity: int
    status: str
    restored_stock: int


class OrderResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_from_reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
