from pydantic import BaseModel
from datetime import datetime
from typing import List
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# Pydantic models for API
class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class AdjustStockRequest(BaseModel):
    sku: str
    amount: int


class ReservationRequest(BaseModel):
    sku: str
    quantity: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
    created_at: datetime


class OrderResponse(BaseModel):
    id: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    page: int
    size: int
    total: int


# SQLAlchemy ORM models
class SKUModel(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, nullable=False)
    stock = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReservationModel(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    sku = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    idempotency_key = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class OrderModel(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
