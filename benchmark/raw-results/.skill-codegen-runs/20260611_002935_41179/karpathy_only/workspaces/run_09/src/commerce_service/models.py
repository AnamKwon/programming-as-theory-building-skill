"""Database and API models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SKUModel(Base):
    """SKU database model."""

    __tablename__ = "skus"

    sku = Column(String, primary_key=True)
    initial_stock = Column(Integer, nullable=False)
    available_stock = Column(Integer, nullable=False)


class ReservationModel(Base):
    """Reservation database model."""

    __tablename__ = "reservations"

    id = Column(String, primary_key=True)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(String, nullable=False)


class OrderModel(Base):
    """Order database model."""

    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    reservation_id = Column(String, nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(String, nullable=False)


# Pydantic request/response models


class CreateSKURequest(BaseModel):
    """Request to create a SKU."""

    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    """Request to adjust stock."""

    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
    """Request to create a reservation."""

    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    """Reservation response."""

    id: str
    sku: str
    quantity: int
    status: str
    created_at: str
    idempotency_key: str


class OrderResponse(BaseModel):
    """Order response."""

    id: str
    reservation_id: str
    sku: str
    quantity: int
    created_at: str


class PaginatedOrdersResponse(BaseModel):
    """Paginated orders response."""

    page: int
    size: int
    total: int
    orders: list[OrderResponse]


class StockResponse(BaseModel):
    """Stock adjustment response."""

    sku: str
    available_stock: int
