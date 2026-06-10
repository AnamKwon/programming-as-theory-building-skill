from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class CreateSkuRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)


class SkuResponse(BaseModel):
    id: int
    code: str
    name: str

    model_config = {"from_attributes": True}


class StockAdjustmentRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., ge=-1000000, le=1000000)


class StockResponse(BaseModel):
    sku_id: int
    quantity_available: int

    model_config = {"from_attributes": True}


class CreateReservationRequest(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0, le=1000000)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    order_id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    reservations: list[ReservationResponse]

    model_config = {"from_attributes": True}


class PaginatedOrdersResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str
