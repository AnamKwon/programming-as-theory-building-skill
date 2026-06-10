from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SKU(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, index=True)
    available_stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, unique=True, index=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class SKUCreate(BaseModel):
    sku: str
    initial_stock: int


class StockAdjust(BaseModel):
    sku: str
    amount: int


class ReservationCreate(BaseModel):
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
    reservation_id: int
    sku: str
    quantity: int
    created_at: datetime
