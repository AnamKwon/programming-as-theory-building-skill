from datetime import datetime
from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku_name: str = Field(..., min_length=1, max_length=100)
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    id: int
    sku_name: str
    available_stock: int
    reserved_stock: int


class StockAdjustment(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity_delta: int = Field(..., ne=0)


class ReservationCreate(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=256)


class ReservationResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime
    idempotency_key: str


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    status: str
    created_at: datetime


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int
