"""Pydantic models for request/response validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    """Status of a reservation."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    """Status of an order."""
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SKUCreate(BaseModel):
    """Request to create a SKU."""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)


class SKUResponse(BaseModel):
    """Response with SKU details."""
    id: int
    code: str
    name: str
    stock: int
    reserved: int

    @property
    def available(self) -> int:
        """Calculate available inventory."""
        return self.stock - self.reserved

    class Config:
        from_attributes = True


class StockAdjustmentRequest(BaseModel):
    """Request to adjust stock."""
    adjustment: int = Field(..., description="Positive or negative adjustment amount")


class ReservationCreateRequest(BaseModel):
    """Request to create a reservation."""
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0, le=10000)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class ReservationResponse(BaseModel):
    """Response with reservation details."""
    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Response with order details."""
    id: int
    reservation_id: int
    status: OrderStatus
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedOrderResponse(BaseModel):
    """Paginated order response."""
    items: list[OrderResponse]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
