from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class CreateSKURequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    name: str
    quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., ge=-999999, le=999999)


class CreateReservationRequest(BaseModel):
    sku_id: int
    quantity: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: Literal["pending", "confirmed", "cancelled", "expired"]
    idempotency_key: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderItemResponse(BaseModel):
    reservation_id: int
    sku_id: int
    quantity: int
    status: Literal["pending", "confirmed", "cancelled", "expired"]

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    status: Literal["reserved", "confirmed", "cancelled"]
    items: list[OrderItemResponse]
    total_quantity: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrdersListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
