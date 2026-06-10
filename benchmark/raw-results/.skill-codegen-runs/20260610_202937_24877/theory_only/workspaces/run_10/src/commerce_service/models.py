from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SKURequest(BaseModel):
    sku: str
    initial_stock: int = Field(gt=0)


class SKUResponse(BaseModel):
    sku: str
    available_stock: int
    created_at: datetime


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    available_stock: int


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
    sku: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class ErrorResponse(BaseModel):
    detail: str
