from datetime import datetime
from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int = Field(gt=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    available_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class AdjustStockResponse(BaseModel):
    sku: str
    updated_stock: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    idempotency_key: str


class ConfirmReservationResponse(BaseModel):
    id: int
    status: str
    order_id: int


class CancelReservationResponse(BaseModel):
    id: int
    status: str
    restored_stock: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    page: int
    size: int
    total: int
    orders: list[OrderResponse]


class HealthResponse(BaseModel):
    status: str
