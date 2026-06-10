from datetime import datetime
from pydantic import BaseModel, Field


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int = Field(..., ge=0)


class SKUResponse(BaseModel):
    sku: str
    available_stock: int
    reserved_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class StockResponse(BaseModel):
    sku: str
    available_stock: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int = Field(..., gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    status: str
    created_at: datetime
    idempotency_key: str


class ConfirmReservationRequest(BaseModel):
    pass


class OrderResponse(BaseModel):
    id: str
    sku: str
    quantity: int
    status: str
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int
