from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"


class SKUCreate(BaseModel):
    sku_code: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku_code: str
    quantity: int
    created_at: datetime


class StockAdjustment(BaseModel):
    delta: int = Field(..., description="Positive or negative quantity change")


class ReservationCreate(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: str
    expires_at: Optional[datetime]
    created_at: datetime


class ReservationConfirm(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    state: str
    created_at: datetime


class OrderList(BaseModel):
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int
