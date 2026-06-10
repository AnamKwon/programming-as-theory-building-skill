from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1)
    stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku: str
    stock: int
    reserved: int
    available: int
    created_at: datetime


class AdjustStockRequest(BaseModel):
    adjustment: int


class ReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    status: ReservationStatus
    customer_id: str
    idempotency_key: str
    created_at: datetime
    expires_at: datetime


class ConfirmReservationRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)


class ConfirmReservationResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    status: ReservationStatus
    customer_id: str
    order_id: str
    created_at: datetime
    confirmed_at: datetime


class OrderResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    customer_id: str
    reservation_id: str
    created_at: datetime
    confirmed_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
