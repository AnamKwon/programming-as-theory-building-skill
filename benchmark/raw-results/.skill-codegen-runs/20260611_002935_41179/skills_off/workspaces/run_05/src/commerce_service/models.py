from pydantic import BaseModel
from datetime import datetime


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    id: int
    sku: str
    stock: int
    created_at: datetime

    class Config:
        from_attributes = True


class StockAdjustRequest(BaseModel):
    sku: str
    amount: int


class StockAdjustResponse(BaseModel):
    sku: str
    new_stock: int


class ReservationCreate(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime
    idempotency_key: str

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str


class PaginationMeta(BaseModel):
    page: int
    size: int
    total: int
    total_pages: int


class OrderListResponse(BaseModel):
    data: list[OrderResponse]
    meta: PaginationMeta
