from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class SKU(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    sku = Column(String(255), unique=True, nullable=False)
    stock_level = Column(Integer, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, nullable=False)
    sku_code = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False)
    idempotency_key = Column(String(255), unique=True, nullable=True)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)


class SKURequest(BaseModel):
    sku: str
    initial_stock: int


class StockAdjustRequest(BaseModel):
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

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    created_at: datetime

    class Config:
        from_attributes = True


def get_db_engine(db_path: str = "commerce.db"):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def init_db(engine):
    Base.metadata.create_all(engine)
