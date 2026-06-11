from datetime import datetime
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    sku: str
    available_stock: int
    reserved_stock: int


class StockAdjustRequest(BaseModel):
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
    created_at: datetime
    idempotency_key: str


class ReservationConfirm(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    total: int
    page: int
    size: int
    orders: list[OrderResponse]


class HealthResponse(BaseModel):
    status: str
