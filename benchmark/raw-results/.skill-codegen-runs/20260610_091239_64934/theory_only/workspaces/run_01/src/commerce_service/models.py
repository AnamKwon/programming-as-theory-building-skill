from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Domain models (internal representation)
class SKU:
    def __init__(self, sku_id: str, available_stock: int, reserved_stock: int = 0):
        self.sku_id = sku_id
        self.available_stock = available_stock
        self.reserved_stock = reserved_stock

    def can_reserve(self, quantity: int) -> bool:
        return self.available_stock >= quantity

    def reserve(self, quantity: int) -> None:
        if not self.can_reserve(quantity):
            raise ValueError(f"Insufficient stock for {self.sku_id}")
        self.available_stock -= quantity
        self.reserved_stock += quantity

    def release(self, quantity: int) -> None:
        self.reserved_stock -= quantity
        self.available_stock += quantity


class Reservation:
    def __init__(
        self,
        reservation_id: str,
        sku_id: str,
        quantity: int,
        state: ReservationState = ReservationState.PENDING,
        created_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ):
        self.reservation_id = reservation_id
        self.sku_id = sku_id
        self.quantity = quantity
        self.state = state
        self.created_at = created_at or datetime.utcnow()
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def confirm(self) -> None:
        if self.state != ReservationState.PENDING:
            raise ValueError(f"Cannot confirm {self.state} reservation")
        self.state = ReservationState.CONFIRMED

    def cancel(self) -> None:
        if self.state == ReservationState.CANCELLED:
            return
        self.state = ReservationState.CANCELLED


class Order:
    def __init__(
        self,
        order_id: str,
        reservation_ids: list[str],
        state: OrderState = OrderState.PENDING,
        created_at: Optional[datetime] = None,
    ):
        self.order_id = order_id
        self.reservation_ids = reservation_ids
        self.state = state
        self.created_at = created_at or datetime.utcnow()

    def confirm(self) -> None:
        if self.state != OrderState.PENDING:
            raise ValueError(f"Cannot confirm {self.state} order")
        self.state = OrderState.CONFIRMED

    def complete(self) -> None:
        if self.state not in (OrderState.PENDING, OrderState.CONFIRMED):
            raise ValueError(f"Cannot complete {self.state} order")
        self.state = OrderState.COMPLETED


# Request/response schemas
class CreateSKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    initial_stock: int = Field(..., gt=0)


class SKUResponse(BaseModel):
    sku_id: str
    available_stock: int
    reserved_stock: int


class AdjustStockRequest(BaseModel):
    adjustment: int = Field(..., description="Positive to add, negative to remove")


class StockAdjustmentResponse(BaseModel):
    sku_id: str
    available_stock: int
    reserved_stock: int


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)
    ttl_seconds: int = Field(default=300, ge=1)

    @field_validator("ttl_seconds")
    @classmethod
    def validate_ttl(cls, v: int) -> int:
        if v > 86400:
            raise ValueError("TTL cannot exceed 24 hours")
        return v


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    state: ReservationState
    created_at: datetime
    expires_at: Optional[datetime]


class ConfirmReservationRequest(BaseModel):
    reservation_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)


class CancelReservationRequest(BaseModel):
    reservation_id: str = Field(..., min_length=1)


class CreateOrderRequest(BaseModel):
    reservation_ids: list[str] = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    order_id: str
    reservation_ids: list[str]
    state: OrderState
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str = "healthy"
