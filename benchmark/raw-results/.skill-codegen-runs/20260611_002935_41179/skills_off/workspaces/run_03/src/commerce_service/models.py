from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str = Field(..., description="Stock Keeping Unit identifier")
    initial_stock: int = Field(..., ge=0, description="Initial stock quantity")


class AdjustStockRequest(BaseModel):
    sku: str = Field(..., description="Stock Keeping Unit identifier")
    amount: int = Field(..., description="Amount to adjust (positive or negative)")


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., description="Stock Keeping Unit identifier")
    quantity: int = Field(..., gt=0, description="Quantity to reserve")
    idempotency_key: str = Field(..., description="Unique idempotency key")


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    updated_at: datetime
    idempotency_key: str

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
