"""Database models and Pydantic schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SKUModel(Base):
    """SKU database model."""

    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False)
    total_stock = Column(Integer, nullable=False)
    reserved_stock = Column(Integer, default=0)

    @property
    def available_stock(self) -> int:
        return self.total_stock - self.reserved_stock


class ReservationModel(Base):
    """Reservation database model."""

    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False)


class OrderModel(Base):
    """Order database model."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)


class CreateSKURequest(BaseModel):
    """Request to create a SKU."""

    sku: str
    initial_stock: int = Field(ge=0)


class SKUResponse(BaseModel):
    """Response containing SKU information."""

    id: int
    sku: str
    total_stock: int
    reserved_stock: int
    available_stock: int


class AdjustStockRequest(BaseModel):
    """Request to adjust stock."""

    sku: str
    amount: int


class AdjustStockResponse(BaseModel):
    """Response after stock adjustment."""

    sku: str
    total_stock: int
    available_stock: int


class CreateReservationRequest(BaseModel):
    """Request to create a reservation."""

    sku: str
    quantity: int = Field(gt=0)
    idempotency_key: str


class ReservationResponse(BaseModel):
    """Response containing reservation details."""

    id: int
    sku: str
    quantity: int
    status: Literal["PENDING", "CONFIRMED", "CANCELLED", "EXPIRED"]
    created_at: datetime
    idempotency_key: str


class OrderResponse(BaseModel):
    """Response containing order details."""

    id: int
    reservation_id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    """Response containing paginated orders."""

    orders: list[OrderResponse]
    page: int
    size: int
    total: int


def get_engine(database_url: str = "sqlite:///commerce.db"):
    """Create and return a database engine."""
    return create_engine(database_url, connect_args={"check_same_thread": False})
