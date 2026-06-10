from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class SKURequest(BaseModel):
    sku: str
    initial_stock: int = Field(gt=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    stock: int


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    stock: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime


class PaginatedOrders(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
