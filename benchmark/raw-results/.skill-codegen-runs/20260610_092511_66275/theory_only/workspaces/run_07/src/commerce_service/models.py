from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderState(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


# Request/Response Models

class SKURequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., gt=0)


class SKUResponse(BaseModel):
    id: int
    sku: str
    name: str
    price: float
    created_at: datetime


class StockAdjustRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=-1000000, le=1000000)


class StockResponse(BaseModel):
    sku_id: int
    available: int
    reserved: int
    total: int


class ReservationRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    state: ReservationState
    expires_at: datetime
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    state: OrderState
    created_at: datetime


class PaginatedOrderResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


# Database Models (internal)

class DBSku:
    def __init__(self, id: int, sku: str, name: str, price: float, created_at: datetime):
        self.id = id
        self.sku = sku
        self.name = name
        self.price = price
        self.created_at = created_at


class DBStock:
    def __init__(self, sku_id: int, available: int, reserved: int):
        self.sku_id = sku_id
        self.available = available
        self.reserved = reserved

    @property
    def total(self) -> int:
        return self.available + self.reserved


class DBReservation:
    def __init__(
        self,
        id: int,
        sku_id: int,
        quantity: int,
        state: ReservationState,
        expires_at: datetime,
        created_at: datetime,
    ):
        self.id = id
        self.sku_id = sku_id
        self.quantity = quantity
        self.state = state
        self.expires_at = expires_at
        self.created_at = created_at


class DBOrder:
    def __init__(
        self,
        id: int,
        sku_id: int,
        quantity: int,
        state: OrderState,
        created_at: datetime,
    ):
        self.id = id
        self.sku_id = sku_id
        self.quantity = quantity
        self.state = state
        self.created_at = created_at
