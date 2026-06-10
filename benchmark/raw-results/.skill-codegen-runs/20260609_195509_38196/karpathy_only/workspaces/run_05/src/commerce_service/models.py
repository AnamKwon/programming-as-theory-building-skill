from datetime import datetime
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(..., ge=0)


class StockAdjustment(BaseModel):
    quantity_delta: int = Field(...)


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, ge=60)


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    skip: int
    limit: int


class ErrorResponse(BaseModel):
    detail: str
    code: str


class HealthResponse(BaseModel):
    status: str
    version: str
