from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku: str
    quantity: int
    created_at: datetime


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., le=10000, ge=-10000)


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ReservationRequest(BaseModel):
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku: str
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderItemResponse(BaseModel):
    sku: str
    quantity: int


class OrderResponse(BaseModel):
    order_id: str
    status: OrderStatus
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    next_cursor: Optional[str] = None


class ErrorResponse(BaseModel):
    code: str
    message: str


# Database models (in-memory representation)
class DBSku:
    def __init__(self, sku: str, quantity: int, created_at: datetime):
        self.sku = sku
        self.quantity = quantity
        self.created_at = created_at


class DBReservation:
    def __init__(
        self,
        reservation_id: str,
        sku: str,
        quantity: int,
        status: ReservationStatus,
        expires_at: datetime,
        created_at: datetime,
        idempotency_key: str,
    ):
        self.reservation_id = reservation_id
        self.sku = sku
        self.quantity = quantity
        self.status = status
        self.expires_at = expires_at
        self.created_at = created_at
        self.idempotency_key = idempotency_key


class DBOrderItem:
    def __init__(self, sku: str, quantity: int):
        self.sku = sku
        self.quantity = quantity


class DBOrder:
    def __init__(
        self,
        order_id: str,
        status: OrderStatus,
        items: list[DBOrderItem],
        created_at: datetime,
        updated_at: datetime,
    ):
        self.order_id = order_id
        self.status = status
        self.items = items
        self.created_at = created_at
        self.updated_at = updated_at
