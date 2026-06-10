from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

DATABASE_URL = "sqlite:///./commerce.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class SKURecord(Base):
    __tablename__ = "skus"

    id = Column(Integer, primary_key=True)
    sku = Column(String, unique=True, index=True)
    available_stock = Column(Integer, default=0)


class ReservationRecord(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    status = Column(String, default="PENDING")
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderRecord(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, index=True)
    sku = Column(String, index=True)
    quantity = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    sku: str
    quantity: int
    created_at: datetime


class PaginatedOrdersResponse(BaseModel):
    page: int
    size: int
    total: int
    orders: list[OrderResponse]


class StockAdjustmentResponse(BaseModel):
    sku: str
    available_stock: int


class HealthResponse(BaseModel):
    status: str
