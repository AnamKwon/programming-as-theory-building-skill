from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    name: str
    current_stock: int


class StockAdjustment(BaseModel):
    delta: int = Field(..., ne=0)


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: Literal["created", "confirmed", "cancelled"]
    expires_at: datetime


class ConfirmationResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: Literal["pending", "confirmed", "cancelled"]


class CancellationResponse(BaseModel):
    status: Literal["cancelled"]


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: Literal["pending", "confirmed", "cancelled"]
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
