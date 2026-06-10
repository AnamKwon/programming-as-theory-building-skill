from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SKURequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class SKUResponse(BaseModel):
    sku_id: str
    name: str


class StockAdjustRequest(BaseModel):
    quantity: int = Field(..., description="Positive or negative adjustment")


class StockResponse(BaseModel):
    sku_id: str
    available: int
    reserved: int


class ReservationCreateRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    reservation_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime


class ReservationConfirmRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    order_id: str
    sku_id: str
    quantity: int
    status: str
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    next_cursor: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
