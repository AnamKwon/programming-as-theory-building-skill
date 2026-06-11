from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False, index=True)
    available_stock = Column(Integer, nullable=False, default=0)
    reserved_stock = Column(Integer, nullable=False, default=0)

    reservations = relationship("Reservation", back_populates="sku_record")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)

    sku_record = relationship("SKU", back_populates="reservations")
    order = relationship("Order", uselist=False, back_populates="reservation")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    reservation = relationship("Reservation", back_populates="order")


class CreateSKURequest(BaseModel):
    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class CreateReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reservation_id: int
    created_at: datetime


class SKUResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    available_stock: int
    reserved_stock: int
