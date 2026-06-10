from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class CreateSKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    initial_stock: int = Field(..., ge=0)


class AdjustStockRequest(BaseModel):
    quantity: int = Field(..., description="Positive or negative adjustment")


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    units: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku: str
    units: int
    state: ReservationState
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    order_id: str
    sku: str
    units: int
    created_at: datetime
    confirmed_at: datetime


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    detail: str
    code: str
