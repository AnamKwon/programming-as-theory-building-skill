from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"


class SKUCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    id: int
    name: str
    created_at: datetime


class StockAdjustRequest(BaseModel):
    delta: int = Field(..., description="Amount to adjust (positive or negative)")


class StockResponse(BaseModel):
    sku_id: int
    quantity: int
    updated_at: datetime


class ReservationCreateRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, ge=60, description="Time-to-live in seconds")


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    created_at: datetime
    expires_at: datetime


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sku_id: int
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: int | None


class HealthResponse(BaseModel):
    status: str = "ok"
