from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUCreate(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    name: str
    available_quantity: int
    reserved_quantity: int


class StockAdjust(BaseModel):
    sku_id: int
    quantity_delta: int = Field(..., description="Positive to add, negative to remove")


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime
    expires_at: datetime


class ReservationConfirm(BaseModel):
    order_id: int


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime
    expires_at: datetime | None


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    per_page: int


class HealthResponse(BaseModel):
    status: str
    message: str
