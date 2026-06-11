"""Pydantic models for request/response validation."""

from datetime import datetime
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int = Field(ge=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    stock: int

    class Config:
        from_attributes = True


class StockAdjustment(BaseModel):
    sku: str
    amount: int


class StockAdjustmentResponse(BaseModel):
    sku: str
    stock: int


class ReservationCreate(BaseModel):
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

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
