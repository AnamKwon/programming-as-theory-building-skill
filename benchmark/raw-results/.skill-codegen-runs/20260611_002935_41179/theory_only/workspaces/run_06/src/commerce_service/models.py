"""Pydantic and SQLAlchemy models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# Pydantic Request/Response Models
class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class SKUResponse(BaseModel):
    id: int
    sku: str
    stock: int

    model_config = {"from_attributes": True}


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class AdjustStockResponse(BaseModel):
    sku: str
    new_stock: int

    model_config = {"from_attributes": True}


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    idempotency_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfirmReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    order_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CancelReservationResponse(BaseModel):
    id: int
    status: str

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    page: int
    size: int
    total: int


# SQLAlchemy ORM Models
class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String(255), unique=True, nullable=False)
    stock = Column(Integer, nullable=False, default=0)

    reservations = relationship("Reservation", back_populates="sku_obj")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    sku = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="PENDING")
    idempotency_key = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False)

    sku_obj = relationship("SKU", back_populates="reservations")
    order = relationship("Order", uselist=False, back_populates="reservation")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)

    reservation = relationship("Reservation", back_populates="order")


class IdempotencyLog(Base):
    __tablename__ = "idempotency_log"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String(255), unique=True, nullable=False)
    response_data = Column(String, nullable=False)
