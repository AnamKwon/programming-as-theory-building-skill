"""Data models for request/response and database persistence."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SKU(Base):
    """Database model for SKU (Stock Keeping Unit)."""

    __tablename__ = "skus"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    stock = Column(Integer, nullable=False, default=0)

    reservations = relationship("Reservation", back_populates="sku_obj")


class Reservation(Base):
    """Database model for stock reservations."""

    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    sku = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sku_obj = relationship("SKU", back_populates="reservations")
    order = relationship("Order", back_populates="reservation", uselist=False)


class Order(Base):
    """Database model for orders created from confirmed reservations."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    reservation = relationship("Reservation", back_populates="order")


class CreateSKURequest(BaseModel):
    """Request model for creating a SKU."""

    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    """Request model for adjusting stock."""

    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
    """Request model for creating a reservation."""

    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    """Response model for a reservation."""

    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    """Response model for an order."""

    id: int
    reservation_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class StockResponse(BaseModel):
    """Response model for stock adjustment."""

    sku: str
    stock: int


class PaginatedOrdersResponse(BaseModel):
    """Response model for paginated orders."""

    items: list[OrderResponse]
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
