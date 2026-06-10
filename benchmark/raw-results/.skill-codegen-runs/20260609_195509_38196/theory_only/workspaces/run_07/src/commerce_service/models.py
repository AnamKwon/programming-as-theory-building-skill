"""Data models: Pydantic schemas and SQLAlchemy ORM."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, Field

Base = declarative_base()


class SKU(Base):
    """Inventory record per SKU. Invariant: available + reserved = total."""

    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False, index=True)
    available = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Reservation(Base):
    """Temporary hold on inventory. Expires after 15 minutes."""

    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending, confirmed, expired, cancelled
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class Order(Base):
    """Confirmed reservation. Immutable once created."""

    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False, index=True)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="confirmed")  # confirmed, shipped, cancelled
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class StockAdjustment(Base):
    """Log of manual stock adjustments for audit trail."""

    __tablename__ = "stock_adjustments"
    id = Column(Integer, primary_key=True)
    sku = Column(String, nullable=False, index=True)
    delta = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# Pydantic request/response schemas


class CreateSKURequest(BaseModel):
    sku: str = Field(..., description="SKU identifier")
    quantity: int = Field(..., description="Initial stock quantity", ge=0)


class SKUResponse(BaseModel):
    sku: str
    available: int
    reserved: int
    total: int

    class Config:
        from_attributes = True


class AdjustStockRequest(BaseModel):
    delta: int = Field(..., description="Change in stock (positive or negative)")
    reason: str = Field(..., description="Reason for adjustment")


class CreateReservationRequest(BaseModel):
    sku: str = Field(..., description="SKU to reserve")
    quantity: int = Field(..., description="Quantity to reserve", gt=0)
    idempotency_key: str = Field(..., description="Unique key for idempotency")


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    expires_at: datetime

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
