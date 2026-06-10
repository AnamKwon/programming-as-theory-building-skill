from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class OrderState(str, Enum):
    CREATED = "CREATED"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


class SKUCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku_id: str
    quantity: int


class StockAdjustment(BaseModel):
    delta: int = Field(..., ge=-1000000, le=1000000)


class ReservationCreate(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=256)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    created_at: datetime
    expires_at: datetime


class ReservationConfirm(BaseModel):
    pass


class OrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    sku_id: str
    quantity: int
    state: OrderState
    created_at: datetime
    confirmed_at: datetime | None = None


class OrderList(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int
