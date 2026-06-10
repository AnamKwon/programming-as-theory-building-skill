from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class HealthResponse(BaseModel):
    status: str


class SKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    stock: int


class StockAdjustmentRequest(BaseModel):
    delta: int = Field(..., ne=0)


class ReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime


class ConfirmReservationRequest(BaseModel):
    pass


class CancelReservationRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: OrderStatus
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    limit: int
    offset: int
