from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, Float, Enum as SQLEnum
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELED = "canceled"
    EXPIRED = "expired"


# ============================================================================
# SQLAlchemy ORM Models
# ============================================================================


class SKUEntity(Base):
    __tablename__ = "skus"

    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    quantity_on_hand = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReservationEntity(Base):
    __tablename__ = "reservations"

    id = Column(String(50), primary_key=True)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(SQLEnum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=True)


class OrderEntity(Base):
    __tablename__ = "orders"

    id = Column(String(50), primary_key=True)
    sku_id = Column(String(50), nullable=False)
    quantity = Column(Float, nullable=False)
    reservation_id = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    idempotency_key = Column(String(255), unique=True, nullable=True)


# ============================================================================
# Pydantic Request/Response Models
# ============================================================================


class CreateSKURequest(BaseModel):
    id: str = Field(..., description="Unique SKU identifier")
    name: str = Field(..., description="Human-readable SKU name")
    quantity_on_hand: float = Field(default=0.0, description="Initial stock quantity")


class SKUResponse(BaseModel):
    id: str
    name: str
    quantity_on_hand: float
    created_at: datetime

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    sku_id: str = Field(..., description="SKU to adjust")
    delta: float = Field(..., description="Quantity change (positive or negative)")


class CreateReservationRequest(BaseModel):
    sku_id: str = Field(..., description="SKU to reserve")
    quantity: float = Field(..., description="Quantity to reserve")
    idempotency_key: Optional[str] = Field(None, description="Prevents duplicate reservations")


class ReservationResponse(BaseModel):
    id: str
    sku_id: str
    quantity: float
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class ConfirmReservationRequest(BaseModel):
    idempotency_key: Optional[str] = Field(None, description="Prevents duplicate confirmations")


class OrderResponse(BaseModel):
    id: str
    sku_id: str
    quantity: float
    reservation_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ErrorResponse(BaseModel):
    detail: str
    code: str
