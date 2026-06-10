"""Data models for the commerce service."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ============================================================================
# SQLAlchemy ORM Models
# ============================================================================


class SkuORM(Base):
    """SKU (Stock Keeping Unit) database model."""

    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku_code = Column(String(255), unique=True, nullable=False, index=True)
    stock_quantity = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReservationORM(Base):
    """Reservation database model."""

    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OrderORM(Base):
    """Order database model."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False, index=True)
    status = Column(String(50), default="CREATED", nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ============================================================================
# Pydantic Request/Response Models
# ============================================================================


class ReservationStatus(str, Enum):
    """Reservation lifecycle states."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderStatus(str, Enum):
    """Order lifecycle states."""

    CREATED = "CREATED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class CreateSkuRequest(BaseModel):
    """Request to create a SKU."""

    sku_code: str = Field(..., min_length=1, max_length=255)
    initial_stock: int = Field(default=0, ge=0)


class SkuResponse(BaseModel):
    """Response containing SKU details."""

    id: int
    sku_code: str
    stock_quantity: int
    created_at: datetime


class StockAdjustmentRequest(BaseModel):
    """Request to adjust stock quantity."""

    quantity_delta: int = Field(...)


class CreateReservationRequest(BaseModel):
    """Request to create a reservation."""

    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    ttl_seconds: int = Field(default=3600, gt=0, le=86400)


class ReservationResponse(BaseModel):
    """Response containing reservation details."""

    id: int
    sku_id: int
    quantity: int
    status: ReservationStatus
    idempotency_key: str
    expires_at: datetime
    created_at: datetime


class ConfirmReservationRequest(BaseModel):
    """Request to confirm a reservation."""

    pass


class CancelReservationRequest(BaseModel):
    """Request to cancel a reservation."""

    pass


class OrderResponse(BaseModel):
    """Response containing order details."""

    id: int
    reservation_id: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime


class PaginatedOrdersResponse(BaseModel):
    """Response containing paginated orders."""

    items: list[OrderResponse]
    cursor: str | None
    has_more: bool


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    error_code: str | None = None


def init_db(db_url: str = "sqlite:///commerce.db") -> None:
    """Initialize the database with all tables."""
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
